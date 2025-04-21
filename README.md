# reimagined-barnacle
A2A protocol playground

## Setup
We will be cloning only the folders from A2A/samples/python/common from the [official A2A repository](google.github.io/A2A/).

First: fork the repository into your own account!
Then type the following commands:
```
git clone --depth 1 https://github.com/your-username/A2A.git A2A
cd A2A
git sparse-checkout init --cone #enable sparse checkout
git sparse-checkout set samples/python/common #set sparse checkout for common folder
git checkout #checkout the files
mv samples/python/common . #move all scripts from the common folder into the root
rm -rf samples  # optional: remove the extra 'samples' folder #remove the samples folder
```