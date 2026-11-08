# Installing on a microscope PC

Two steps. The second one needs no internet, so the microscope PC never has to be online.

1. **On any Windows computer with internet**: get this folder and run `download.bat`.
   It asks whether the microscope PC has an NVIDIA graphics card (GPU build of torch, about
   2.5 GB, or CPU build, about 200 MB) and fills the folder `env\` with a portable Python,
   every package and the cellpose model.
2. **Copy the whole folder** to the microscope PC, where it is going to stay, for example
   `D:\automation`. The path must not contain spaces.
3. **On the microscope PC**: run `install.bat`. It asks for
   - the folder ZEN runs its macros from - `ZeissAPI` is copied there;
   - the folder ZEN autosaves to (FCS `.fcs`/`.raw` files), only on the first install.

   It writes `ZeissAPI\config\path_config.json` in ZEN's folder, and at the end runs the analysis
   once on a test image to show that everything works.

Run `install.bat` again after updating or moving the folder. It replaces `ZeissAPI` in ZEN's
folder (it asks first) but keeps that machine's `path_config.json`. Edits made directly in ZEN's
copy of `ZeissAPI` are lost then - make them in this folder.
