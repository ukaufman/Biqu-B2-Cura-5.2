# Biqu-B2-Cura-5.2
Cura 5.2.2 Plugins for BigTree Biqu B2 3D Printer.

Since BigTree Tech does not actively support newer Cura releases for their 3D printers I took the liverty to retrofit the plugins they provide in their GitHub Repository to take advantage of the massive slicing algorithm improvements of V5.2.

The main things that I had to change have to do with the syntax differences from PyQt5 to PyQt6, in which the Cura 5.x interface is built.

## Testing PC specs
- Lenovo Thinkpad E495.
- Ryzen 7 3700U CPU.
- 32 GB of RAM.
- 256 GB main NVMe SSD.
- Windows 11 22H2.
- Bigtree Tech. Biqu B2 3D Printer.

## Base plugins
- Taken from https://github.com/bigtreetech/BIQU-B2 - commit 4013cf3.

## How to install the plugins
- Close Cura if running.
- Copy the folders inside 'plugin' folder to %appdata%/cura/5.2/plugins.
- That's all.

I hope it is useful for somebody. All rights

## Credits
- [BigTree Tech.](https://github.com/bigtreetech/BIQU-B2) They are the manufacturers of the printer and they coded the plugins, I just adapted it to Cura 5.2
