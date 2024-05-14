#!/usr/bin/env python3
import argparse
import os
import queue
import subprocess
import sys
import json
import logging
import signal
import threading
import tarfile
import tempfile


MAX_THREADS = 8

THREAD_LOCK = threading.Lock()
JUJU_KEY = "~/.local/share/juju/ssh/juju_id_rsa"
USER_KEY = "~/.ssh/id_rsa"
data_dir = tempfile.mkdtemp(prefix="hotsos-collection-")


def terminator(signum, frame):
    raise TimeoutError()


class SSHExecutor(object):
    def __init__(self, host, user, key, timeout):
        self.host = host
        self.user = user
        self.key = key
        self.timeout = timeout
        self.connected = False

    def run(self, cmd, log_handler=None, parent_caller=None):
        out = err = None

        ssh_cmd = [
            'ssh',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            '-i', self.key,
            f'{self.user}@{self.host}',
            cmd
        ]

        try:
            parent_caller.print_status(msg=f"Running: {' '.join(ssh_cmd)}")

            with subprocess.Popen(ssh_cmd, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  universal_newlines=True) as process:
                def read_stdout():
                    nonlocal out
                    parent_caller.print_status(msg="read_stdout started")
                    for line in iter(process.stdout.readline, ''):
                        if log_handler:
                            log_handler.write(line)
                        out += line
                    parent_caller.print_status(msg="read_stdout finished")

                # Thread to read and write stderr
                def read_stderr():
                    nonlocal err
                    parent_caller.print_status(msg="read_stderr started")
                    for line in iter(process.stderr.readline, ''):
                        if log_handler:
                            log_handler.write(line)
                        err += line
                    parent_caller.print_status(msg="read_stderr finished")

                out = err = ''

                # Start the threads
                stdout_thread = threading.Thread(target=read_stdout)
                stderr_thread = threading.Thread(target=read_stderr)

                parent_caller.print_status(msg="before thread running")
                stdout_thread.start()
                stderr_thread.start()
                process_timer = threading.Timer(self.timeout,
                                                lambda: process.kill())
                process_timer.start()
                process.wait()
                process_timer.cancel()
                stdout_thread.join()
                stderr_thread.join()
        except subprocess.TimeoutExpired:
            err = 'Command execution timed out.'
        except subprocess.CalledProcessError as e:
            err = str(e)

        return out, err


class CollectorTask(object):

    def __init__(self, app, machine, args, priv_key=JUJU_KEY):
        self.app = app
        self.result = None
        self.machine = machine
        self.args = args
        self.status = "NOT STARTED"
        self.executor = SSHExecutor(
            machine[1], "ubuntu", os.path.expanduser(priv_key),
            self.args.timeout)
        self.log_file = None

        if self.args.debug:
            log_name = "{}_{}.log".format(
                self.app, self.machine[0].replace("/", "-"))
            self.log_file = os.path.join(data_dir, log_name)
            with open(self.log_file, "w") as f:
                f.write("")

    def __str__(self):
        return "CollectorTask: app: {}, machine: {}, status: {}".format(
            self.app, self.machine[0], self.status)

    def print_status(self, msg=None):
        if msg:
            fmt = "{}: {}".format(self, msg)
        else:
            fmt = "{}".format(self)
        with THREAD_LOCK:
            LOG.debug(fmt)

    def _run(self, cmd):
        if self.args.debug:
            with open(self.log_file, "a") as f:
                out, err = self.executor.run(cmd, log_handler=f,
                                             parent_caller=self)
                f.write("CMD: {}\n".format(cmd))
                f.write("OUT: {}\n".format(out))
                f.write("ERR: {}\n\n".format(err))
        else:
            out, err = self.executor.run(cmd, log_handler=None,
                                         parent_caller=self)

        return out, err

    def setup(self):
        self.status = "SETUP"
        self.print_status()
        try:
            out, _ = self._run("hostname")
            if out is not None:
                self.executor.connected = True
            else:
                self.executor.connected = False
                self.status = "FAILED"
                return
        except Exception as e:
            self.status = "FAILED"
            self.executor.connected = False
            self.print_status(msg="Failed to connect to host: {}".format(
                self.machine[1]))
            self.print_status(msg=str(e))
            return

        if self.args.use_apt:
            self._setup_apt()
        else:
            self._setup_pipx()

    def _setup_pipx(self):
        self._run("sudo apt update")
        self._run("sudo apt install -y python3-venv pipx")
        self._run("sudo pipx install hotsos")

    def _teardown_pipx(self):
        self._run("sudo pipx uninstall hotsos")

    def _setup_apt(self):
        self._run("sudo add-apt-repository ppa:ubuntu-support-team/hotsos")
        self._run("sudo apt update")
        self._run("sudo apt install -y hotsos")

    def _teardown_apt(self):
        self._run("sudo apt remove -y hotsos")
        self._run("sudo add-apt-repository --remove "
                  "ppa:ubuntu-support-team/hotsos")

    def teardown(self):
        self.status = "TEARDOWN"
        self.print_status()

        if self.args.use_apt:
            self._teardown_apt()
        else:
            self._teardown_pipx()

    def collect(self):

        if self.args.use_apt:
            hotsos_cmd = "hotsos"
        else:
            root_home_dir = self._run("sudo bash -c 'echo $HOME'")[0]
            hotsos_cmd = "{}/.local/bin/hotsos".format(root_home_dir.strip())

        if not self.executor.connected:
            self.status = "FAILED"
            self.print_status(msg="Not collected. Not connected to host.")
            return

        self.status = "COLLECTING"
        self.print_status()
        self.result, _ = self._run(
            "sudo {} --command-timeout {} --max-parallel-tasks {} {} /"
            "".format(hotsos_cmd, self.args.timeout, self.args.workers,
                      "--debug" if self.args.debug else ""))
        self.status = "COLLECTED"
        self.print_status()

    def save(self):
        if self.status != "COLLECTED" or not self.result:
            self.status = "FAILED"
            self.print_status(msg="Not collected. Not connected to host.")
            return

        self.status = "SAVING"
        self.print_status()
        file_name = "{}_{}.yaml".format(
            self.app, self.machine[0].replace("/", "-"))
        with open(os.path.join(data_dir, file_name), "w") as f:
            f.write(self.result)
        self.status = "FINISHED"
        self.print_status()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Collects hotsos in linux hosts. If run without "
                    "parameters, will "
                    "probe the applications from the current juju model, and "
                    "collect hotsos from 1 unit per application.")
    parser.add_argument("--workers", type=int, default=8,
                        help="Number of workers (default: 8).")
    parser.add_argument("--timeout", type=int, default=1800,
                        help="Max time to wait for hotsos command in the "
                             "units (default: 900).")
    parser.add_argument("--all-units", action="store_true",
                        help="Include all units from the defined applications "
                             "(default: False). Ignored if "
                             "--host-ips is specified.")
    parser.add_argument("--host-ips", type=str, default=None,
                        help="Specific host IPs to include (default: None). "
                             "Has precedence over --apps. Assumes that the "
                             "hosts have SSH keys configured and passwordless "
                             "sudo access.")
    parser.add_argument("--apps", type=str, default=None,
                        help="Specific apps to include (default: None). In the"
                             "case where nothing is specified all applications"
                             "will be run.")
    parser.add_argument("--exclude-apps", type=str, default=None,
                        help="Specific apps to exclude (default: None). "
                             "Discarded if --apps or --host-ips are "
                             "specified.")
    parser.add_argument("--status-file", type=str,
                        help="A json juju status output, for debugging "
                             "purposes only.")
    parser.add_argument("--ssh-key", type=str, default=JUJU_KEY,
                        help="Path to the ssh private key (default: "
                             "{}).".format(JUJU_KEY))
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging (default: False).")
    parser.add_argument("--use-apt", action="store_true",
                        help="Use dpkg instead of pipx to install hotsos "
                             "(default: False).")
    return parser.parse_args()


def configure_logging():
    logger = logging.getLogger(__name__)
    log_formatter = logging.Formatter(
        "%(asctime)s %(levelname)s: %(message)s")

    file_handler = logging.FileHandler(
        os.path.join(data_dir, "hotsos-collector.log"))
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)

    log_formatter = logging.Formatter("%(message)s")
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(log_formatter)
    logger.addHandler(stream_handler)

    logger.setLevel(logging.DEBUG)

    return logger


LOG = configure_logging()


def process_juju_status(status):
    principle_charm_apps = {}
    machines = {}

    if not status:
        return principle_charm_apps, machines

    applications = status.get("applications", {})
    for app_name, app_data in applications.items():
        charm_units = app_data.get("units", {})
        app_machines = []
        for unit_data in charm_units.values():
            try:
                app_machines.append((unit_data["machine"],
                                     unit_data["public-address"],
                                     unit_data["leader"]))
            except KeyError:
                # The unit doesn't have a leader key, so it's not a leader
                app_machines.append((unit_data["machine"],
                                     unit_data["public-address"],
                                     False))

        if app_machines:
            principle_charm_apps[app_name] = app_machines

    machines_data = status.get("machines", {})
    for machine_name, machine_data in machines_data.items():
        dns_name = machine_data.get("dns-name")
        hostname = machine_data.get("instance-id")
        machines[machine_name] = (hostname, dns_name)

    return principle_charm_apps, machines


def get_target_machines(principle_charm_apps, all_machines,
                        probe_all_units=False, probe_apps=None,
                        probe_host_ips=None, exclude_apps=None):
    """Returns a list of tuples (app_name, machine) to probe.

    """

    targets = []

    def _get_leader_unit(unit_list):
        for unit in unit_list:
            if unit[2]:
                return unit

        return unit_list[0]

    if probe_host_ips:
        host_ips = set(probe_host_ips.split(','))
        for host, hid in zip(host_ips, range(len(host_ips))):
            targets.append(('host' + str(hid), (host, host)))

        return targets

    if probe_apps:
        for app in probe_apps.split(','):
            try:
                if probe_all_units:
                    for machine in principle_charm_apps[app]:
                        targets.append((app, machine))
                else:
                    leader = _get_leader_unit(principle_charm_apps[app])
                    targets.append((app, leader))
            except KeyError:
                LOG.error("App %s not found in status", app)
                sys.exit(1)

        return targets

    if probe_all_units:
        for app, machines in principle_charm_apps.items():
            for machine in machines:
                targets.append((app, machine))
    else:
        for app in principle_charm_apps.keys():
            leader = _get_leader_unit(principle_charm_apps[app])
            targets.append((app, leader))

    if exclude_apps:
        for app in exclude_apps.split(','):
            targets = [target for target in targets if target[0] != app]

    # We need to make sure that we also run in machines/controllers that are
    # pure LXD hosts, i.e., don't have any application associated with them,
    # e.g. a controller only running apps on containers.
    covered_machines = []
    for app, machines in principle_charm_apps.items():
        for machine in machines:
            if 'lxd' not in machine[0]:
                covered_machines.append(machine[0])

    controller_machines_ids = [machine for machine in all_machines.keys()
                               if machine not in covered_machines]
    controllers = []
    for mid, data in all_machines.items():
        if mid in controller_machines_ids:
            controllers.append(('controller', (mid, data[1])))

    if controllers:
        targets = targets + controllers

    return targets


def worker(task_queue, started_tasks, uncomplete_tasks, complete_tasks):
    thread_name = threading.current_thread().name
    with THREAD_LOCK:
        LOG.debug("Starting thread: %s", thread_name)

    while True:
        with THREAD_LOCK:
            if task_queue.empty():
                LOG.debug("Thread %s exiting", thread_name)
                break
            collector = task_queue.get()
            LOG.debug("Thread %s entering for task", thread_name)
            LOG.info("Collecting hotsos reports for %s, machine: %s",
                     collector.app, collector.machine[0])

        with THREAD_LOCK:
            started_tasks.append(collector.machine[0])
            uncomplete_tasks.append(collector.machine[0])

        collector.setup()
        collector.collect()
        collector.save()
        collector.teardown()
        with THREAD_LOCK:
            complete_tasks.append(collector.machine[0])
            uncomplete_tasks.remove(collector.machine[0])
            task_queue.task_done()

        with THREAD_LOCK:
            LOG.info(
                "Finished collection for %s, machine: %s. %s targets "
                "unfinished.", collector.app, collector.machine[0],
                task_queue.unfinished_tasks)
            LOG.info("Started: %s, Completed: %s, Unfinished: %s",
                     ','.join(started_tasks), ','.join(complete_tasks),
                     ','.join(uncomplete_tasks))

    with THREAD_LOCK:
        LOG.debug("Finishing thread: %s", thread_name)


def main():
    args = parse_args()
    priv_key = args.ssh_key

    def _pack_results():
        tar_file = os.path.join(data_dir + ".tar.xz")
        with tarfile.open(tar_file, "w:xz") as tar:
            tar.add(data_dir, arcname=os.path.basename(data_dir))
        LOG.info("Data is stored in %s", tar_file)

    if args.status_file:
        with open(args.status_file, "r") as f:
            status = json.load(f)
    elif args.host_ips:
        status = None
        priv_key = USER_KEY
    else:
        output = subprocess.check_output(["juju", "status"]).decode("utf-8")
        with open(os.path.join(data_dir, "juju-status.txt"), "w") as f:
            f.write(output)
        output = subprocess.check_output(
            ["juju", "status", "--format=json"]).decode("utf-8")
        with open(os.path.join(data_dir, "juju-status.json"), "w") as f:
            f.write(output)

        status = json.loads(output)

    principle_charm_apps, all_machines = process_juju_status(status)
    targets = get_target_machines(principle_charm_apps, all_machines,
                                  args.all_units, args.apps, args.host_ips,
                                  args.exclude_apps)

    LOG.info("Collecting data from %s targets: %s",
             len(targets), ", ".join([target[0] for target in targets]))
    LOG.info("Data and logs will be saved in %s", data_dir)

    task_queue = queue.Queue()
    started_tasks = []
    uncomplete_tasks = []
    complete_tasks = []

    for target in targets:
        task = CollectorTask(target[0], target[1], args, priv_key=priv_key)
        task_queue.put(task)

    threads = []
    for i in range(MAX_THREADS):
        t = threading.Thread(target=worker,
                             args=(task_queue, started_tasks, uncomplete_tasks,
                                   complete_tasks),
                             name=f"CollectorTask-{i+1}")
        t.start()
        threads.append(t)
    with THREAD_LOCK:
        LOG.debug("Main task waiting for task queue to be empty")

    signal.signal(signal.SIGALRM, terminator)
    # add 60 seconds to time out to allow for the hotsos collection to cleanly
    # time out.
    signal.alarm(args.timeout + 60)
    try:
        task_queue.join()
    except TimeoutError:
        LOG.error("Program execution exceeded the specified timeout.")
        _pack_results()
        sys.exit(1)
    finally:
        # Disable the alarm
        signal.alarm(0)

    with THREAD_LOCK:
        LOG.debug("Done")

    for t in threads:
        LOG.debug("Waiting for thread %s to join", t.name)
        t.join()
        LOG.debug("Thread %s joined", t.name)

    _pack_results()


if __name__ == "__main__":
    main()
