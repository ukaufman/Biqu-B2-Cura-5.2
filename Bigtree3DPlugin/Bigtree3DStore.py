# Copyright (c) 2017 Looming
# Cura is released under the terms of the LGPLv3 or higher.

import os
import sys

from PyQt6.QtCore import QUrl,Qt,QSize,QFile, QFileInfo, QIODevice,QTextStream,QByteArray,QStringConverter
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from UM.Application import Application
from UM.Logger import Logger
from UM.Mesh.MeshWriter import MeshWriter
from UM.FileHandler.WriteFileJob import WriteFileJob
from UM.Message import Message

from UM.OutputDevice.OutputDevice import OutputDevice
from UM.OutputDevice import OutputDeviceError
from UM.OutputDevice.OutputDeviceError import WriteRequestFailedError #For when something goes wrong.
from UM.OutputDevice.OutputDevicePlugin import OutputDevicePlugin #The class we need to extend.

from UM.PluginRegistry import PluginRegistry #Getting the location of Hello.qml.

from UM.i18n import i18nCatalog

from cura.CuraApplication import CuraApplication

from cura.Snapshot import Snapshot
from cura.Utils.Threading import call_on_qt_thread

catalog = i18nCatalog("uranium")
CODEC = QStringConverter.Encoding.Utf8

def i4b(n):
    return [n >> 24 & 0xFF,n >> 16 & 0xFF,n >> 8 & 0xFF,n >> 0 & 0xFF]

def i2b(n):
    return [n >> 8 & 0xFF,n >> 0 & 0xFF]

class Bigtree3DStorePlugin(OutputDevicePlugin): #We need to be an OutputDevicePlugin for the plug-in system.
    ##  Called upon launch.
    #
    #   You can use this to make a connection to the device or service, and
    #   register the output device to be displayed to the user.
    def start(self):
        self.getOutputDeviceManager().addOutputDevice(Bigtree3DStore()) #Since this class is also an output device, we can just register ourselves.
        #You could also add more than one output devices here.
        #For instance, you could listen to incoming connections and add an output device when a new device is discovered on the LAN.

    ##  Called upon closing.
    #
    #   You can use this to break the connection with the device or service, and
    #   you should unregister the output device to be displayed to the user.
    def stop(self):
        self.getOutputDeviceManager().removeOutputDevice("Bigtree3D_store_gcode") #Remove all devices that were added. In this case it's only one.

class Bigtree3DStore(OutputDevice): #We need an actual device to do the writing.
    def __init__(self):
        super().__init__("Bigtree3D_store_gcode") #Give an ID which is used to refer to the output device.

        #Optionally set some metadata.
        self.setName("Bigtree3D Store Gcode") #Human-readable name (you may want to internationalise this). Gets put in messages and such.
        self.setShortDescription("Save as Bigtree3D format") #This is put on the save button.
        self.setDescription("Save as Bigtree3D format")
        self.setIconName("save")

        self._writing = False

    @call_on_qt_thread
    def overread(self,msize):
        moutdata = ""
        img = Snapshot.snapshot(width = msize.width(), height = msize.height()).scaled(msize.width(),msize.height(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        moutdata = moutdata + ";"+(hex(msize.width())[2:]).rjust(4,'0')+(hex(msize.height())[2:]).rjust(4,'0')+"\r\n"
        pos = QSize(0,0)
        for ypos in range(0,img.height()):
            qrgb = ";"
            for xpos in range(0,img.width()):
                data = img.pixel(xpos,ypos)
                pos.setWidth(pos.width()+1)
                qrgb = qrgb + (hex(((data & 0x00F80000) >> 8 ) | ((data & 0x0000FC00) >> 5 ) | ((data & 0x000000F8) >> 3 ))[2:]).rjust(4,'0')
            pos.setWidth(0)
            pos.setHeight(pos.height()+1)
            moutdata = moutdata + qrgb + "\r\n"
        return moutdata

    ##  Request the specified nodes to be written to a file.
    #
    #   \param nodes A collection of scene nodes that should be written to the
    #   file.
    #   \param file_name \type{string} A suggestion for the file name to write
    #   to. Can be freely ignored if providing a file name makes no sense.
    #   \param limit_mimetypes Should we limit the available MIME types to the
    #   MIME types available to the currently active machine?
    #   \param kwargs Keyword arguments.
    def requestWrite(self, nodes, file_name = None, limit_mimetypes = None, file_handler = None, **kwargs):
        if self._writing:
            raise OutputDeviceError.DeviceBusyError()

        # Set up and display file dialog
        dialog = QFileDialog()

        dialog.setWindowTitle(catalog.i18nc("@title:window", "Save to File"))
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)

        # Ensure platform never ask for overwrite confirmation since we do this ourselves
        dialog.setOption(QFileDialog.Option.DontConfirmOverwrite)

        if sys.platform == "linux" and "KDE_FULL_SESSION" in os.environ:
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog)

        filters = []
        mime_types = []
        selected_filter = None

        if "preferred_mimetypes" in kwargs and kwargs["preferred_mimetypes"] is not None:
            preferred_mimetypes = kwargs["preferred_mimetypes"]
        else:
            preferred_mimetypes = Application.getInstance().getPreferences().getValue("local_file/last_used_type")
        preferred_mimetype_list = preferred_mimetypes.split(";")

        if not file_handler:
            file_handler = Application.getInstance().getMeshFileHandler()

        file_types = file_handler.getSupportedFileTypesWrite()

        file_types.sort(key = lambda k: k["description"])
        if limit_mimetypes:
            file_types = list(filter(lambda i: i["mime_type"] in limit_mimetypes, file_types))

        file_types = [ft for ft in file_types if not ft["hide_in_file_dialog"]]

        if len(file_types) == 0:
            Logger.log("e", "There are no file types available to write with!")
            raise OutputDeviceError.WriteRequestFailedError(catalog.i18nc("@info:warning", "There are no file types available to write with!"))

        # Find the first available preferred mime type
        preferred_mimetype = None
        for mime_type in preferred_mimetype_list:
            if any(ft["mime_type"] == mime_type for ft in file_types):
                preferred_mimetype = mime_type
                break

        for item in file_types:
            type_filter = "{0} (*.{1})".format(item["description"], item["extension"])
            filters.append(type_filter)
            mime_types.append(item["mime_type"])
            if preferred_mimetype == item["mime_type"]:
                selected_filter = type_filter
                if file_name:
                    file_name += "." + item["extension"]

        # Add the file name before adding the extension to the dialog
        if file_name is not None:
            dialog.selectFile(file_name)

        dialog.setNameFilters(filters)
        if selected_filter is not None:
            dialog.selectNameFilter(selected_filter)

        stored_directory = Application.getInstance().getPreferences().getValue("local_file/dialog_save_path")
        dialog.setDirectory(stored_directory)

        if not dialog.exec():
            raise OutputDeviceError.UserCanceledError()

        save_path = dialog.directory().absolutePath()
        Application.getInstance().getPreferences().setValue("local_file/dialog_save_path", save_path)

        selected_type = file_types[filters.index(dialog.selectedNameFilter())]
        Application.getInstance().getPreferences().setValue("local_file/last_used_type", selected_type["mime_type"])

        # Get file name from file dialog
        file_name = dialog.selectedFiles()[0]
        Logger.log("d", "Writing to [%s]..." % file_name)
        
        if os.path.exists(file_name):
            result = QMessageBox.question(None, catalog.i18nc("@title:window", "File Already Exists"), catalog.i18nc("@label Don't translate the XML tag <filename>!", "The file <filename>{0}</filename> already exists. Are you sure you want to overwrite it?").format(file_name))
            if result == QMessageBox.StandardButton.No.value:
                raise OutputDeviceError.UserCanceledError()

        self.writeStarted.emit(self)

        # Actually writing file
        if file_handler:
            file_writer = file_handler.getWriter(selected_type["id"])
        else:
            file_writer = Application.getInstance().getMeshFileHandler().getWriter(selected_type["id"])

        try:
            mode = selected_type["mode"]
            if mode == MeshWriter.OutputMode.TextMode:
                Logger.log("d", "Writing to Local File %s in text mode", file_name)
                stream = open(file_name, "wt", encoding = "utf-8")
            elif mode == MeshWriter.OutputMode.BinaryMode:
                Logger.log("d", "Writing to Local File %s in binary mode", file_name)
                stream = open(file_name, "wb")
            else:
                Logger.log("e", "Unrecognised OutputMode.")
                return None

            job = WriteFileJob(file_writer, stream, nodes, mode)
            job.setFileName(file_name)
            job.setAddToRecentFiles(True)  # The file will be added into the "recent files" list upon success
            job.progress.connect(self._onJobProgress)
            job.finished.connect(self._onWriteJobFinished)

            message = Message(catalog.i18nc("@info:progress Don't translate the XML tags <filename>!", "Saving to <filename>{0}</filename>").format(file_name),
                              0, False, -1 , catalog.i18nc("@info:title", "Saving"))
            message.show()

            job.setMessage(message)
            self._writing = True
            job.start()
        except PermissionError as e:
            Logger.log("e", "Permission denied when trying to write to %s: %s", file_name, str(e))
            raise OutputDeviceError.PermissionDeniedError(catalog.i18nc("@info:status Don't translate the XML tags <filename>!", "Permission denied when trying to save <filename>{0}</filename>").format(file_name)) from e
        except OSError as e:
            Logger.log("e", "Operating system would not let us write to %s: %s", file_name, str(e))
            raise OutputDeviceError.WriteRequestFailedError(catalog.i18nc("@info:status Don't translate the XML tags <filename> or <message>!", "Could not save to <filename>{0}</filename>: <message>{1}</message>").format()) from e

    @call_on_qt_thread
    def overseek(self):
        outdatar = ""
        tempPath, _ = os.path.split(os.path.realpath(__file__))
        tempPath = os.path.dirname(tempPath)
        CONFIGPATH = os.path.join(tempPath,"ResolutionExtension\\Resolution.txt")
        if QFile(CONFIGPATH).exists() == False:#Default
            outdatar = outdatar + self.overread(QSize(70,70))
            outdatar = outdatar + self.overread(QSize(95,80))
            outdatar = outdatar + self.overread(QSize(95,95))
            outdatar = outdatar + self.overread(QSize(160,140))
        else:
            fh = QFile(CONFIGPATH)
            fh.open(QIODevice.OpenModeFlag.ReadOnly)
            stream = QTextStream(fh)
            stream.setEncoding(CODEC)
            while stream.atEnd() == False:
                tem = stream.readLine()
                if tem[0] == '#':
                    continue
                tems = tem.split(",")
                if len(tems) == 2 and tems[0].isdigit() and tems[1].isdigit():
                    outdatar = outdatar + self.overread(QSize(int(tems[0]),int(tems[1])))
            fh.close()
        return outdatar

    def _onJobProgress(self, job, progress):
        self.writeProgress.emit(self, progress)

    @call_on_qt_thread
    def extruder_M2O(self):
        flag = False
        CONFIGPATH = os.path.join(sys.path[0],"plugins\\ResolutionExtension\\Resolution.txt")
        if QFile(CONFIGPATH).exists() == True:
            fh = QFile(CONFIGPATH)
            fh.open(QIODevice.OpenModeFlag.ReadOnly)
            stream = QTextStream(fh)
            stream.setEncoding(CODEC)
            while stream.atEnd() == False:
                tem = stream.readLine()
                if tem.startswith("# extruder_M2O"):
                    if (tem.split("="))[1].strip().lower() == "yes":
                        flag = True
                    break
            fh.close()
        return flag

    def _onWriteJobFinished(self, job):
        self._writing = False
        self.writeFinished.emit(self)
        wirte_succ = False
        if job.getResult():
            self.writeSuccess.emit(self)
            wirte_succ = True
        else:
            message = Message(catalog.i18nc("@info:status Don't translate the XML tags <filename> or <message>!", "Could not save to <filename>{0}</filename>: <message>{1}</message>").format(job.getFileName(), str(job.getError())), lifetime = 0, title = catalog.i18nc("@info:title", "Warning"))
            message.show()
            self.writeError.emit(self)
        try:
            job.getStream().close()
            if wirte_succ:
                self.do_snap(job.getFileName())
        except (OSError, PermissionError): #When you don't have the rights to do the final flush or the disk is full.
            message = Message(catalog.i18nc("@info:status", "Something went wrong saving to <filename>{0}</filename>: <message>{1}</message>").format(job.getFileName(), str(job.getError())), title = catalog.i18nc("@info:title", "Error"))
            message.show()
            self.writeError.emit(self)

    def _onMessageActionTriggered(self, message, action):
        if action == "open_folder" and hasattr(message, "_folder"):
            QDesktopServices.openUrl(QUrl.fromLocalFile(message._folder))

    @call_on_qt_thread
    def do_snap(self,gfile):
        img = Snapshot.snapshot(width = 200, height = 200).scaled(200,200,Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        outdata = ""
        outdata = outdata + self.overseek()
        outdata = outdata + "; bigtree thumbnail end\r\n\r\n"
        fh = QFile(gfile)
        fh.open(QIODevice.OpenModeFlag.ReadOnly)
        stream = QTextStream(fh)
        stream.setEncoding(CODEC)
        # lino = 0
        fg = stream.readAll() + "\r\n"
        if self.extruder_M2O() == True:
            # fg = fg.replace("G0","G3")
            # fg = fg.replace("G1","G4")
            fg = fg.replace("M104 T1",";M104 T1")
            fg = fg.replace("M104 T0",";M104 T0")
            fg = fg.replace("M109 T0",";M109 T0")
            fg = fg.replace("M109 T1",";M109 T1")
#            fg = fg.replace("M104 T0 S0",";M104 T0 S0")
#            fg = fg.replace("M104 T1 S0",";M104 T1 S0")
#            fg = fg.replace("M109 T0 S0",";M109 T0 S0")
#            fg = fg.replace("M109 T1 S0",";M109 T1 S0")
#            fg = fg.replace("M104 S0",";M104 S0")
#            fg = fg.replace("M109 S0",";M109 S0")
        fh.close()
        bigtree3dfile = os.path.splitext(gfile)[0]+"[Bigtree].gcode"
        fh = QFile(bigtree3dfile)
        fh.open(QIODevice.OpenModeFlag.WriteOnly)
        stream = QTextStream(fh)
        stream.setEncoding(CODEC)
        stream << outdata
        stream << fg
        fh.close()
        os.remove(gfile)

