## Contributing to UA Reviewkit

You can contribute to this repository as follows;

  * clone this repository to your personal launchpad e.g.

    git clone https://git.launchpad.net/ua-reviewkit
    cd ua-reviewkit
    git remote add <your-lp-id> git+ssh://<your-lp-id>@git.launchpad.net/~<your-lp-id>/ua-reviewkit

  * create a branch

    git checkout -b myfeature

  * the contents of this repository are organised as "modules" represented by
    directories at the top level. If you want to contribute to an existing
    module, you can propose patches against it directly or if you want to add
    a new module you can do so by creating a directory as follows:

    ua-reviewkit/staging/<your-lp-id>/<module>

    Adding your contribution under this path. This will be merged to master
    as-is and once it is deemed *ready* it can be moved to the root directory.

  * commit changes and push to launchpad

    git push <yourlpname>

  * To create a merge proposal go to:
    
    https://code.launchpad.net/~<your-lp-id>/ua-reviewkit/+git/ua-reviewkit/+ref/myfeature
    
    And hit "Propose for merging"

    NOTE: if you are not ready for review you can uncheck "Needs Review" to set as Work In Progress

