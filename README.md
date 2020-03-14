## Overview

This repository contains tools, scripts, docs and anything else that might be
helpful to use as part of a UA handover.

## Contributing

You can contribute to this repository as follows;

  * clone this repository to your personal launchpad e.g.

    git clone https://git.launchpad.net/~canonical-support-eng/ua-reviewkit
    cd ua-reviewkit
    git remote add <your-lp-id> git+ssh://<your-lp-id>@git.launchpad.net/~<your-lp-id>/ua-reviewkit

  * create a branch

    git checkout -b myawesomecontrib


  * the contents of this repository are organised as "modules" represented by
    directories at the top level. If you want to contribute to an existing
    module, you can propose patches against it directly. If you want to add
    a new module you can do so by creating a directory as follows:

    ua-reviewkit/staging/<your-lp-id>/<module>

    Adding your contribution under this path. This will be merged to master
    as-is and once it is deemed *ready* it can be moved to the root directory.

  * commit changes and push to launchpad

    git push <yourlpname>

  * propose for merge i.e. go to:
    
    https://code.launchpad.net/~<your-lp-id>/tooling/+git/ua-reviewkit/+ref/myawesomecontrib
    
    And hit "Propose for merging"

