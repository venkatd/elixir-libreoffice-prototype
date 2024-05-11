try:
    import uno
except ImportError:
    raise ImportError(
        "Could not find the 'uno' library. This package must be installed with a Python "
        "installation that has a 'uno' library. This typically means you should install "
        "it with the same Python executable as your Libreoffice installation uses."
    )

import io
import logging
import os
import unohelper

from pathlib import Path
from com.sun.star.beans import PropertyValue
from com.sun.star.io import XOutputStream
import argparse
import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading
import platform
import xmlrpc.server
# from importlib import metadata
from pathlib import Path

sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# from server import unoserver

__version__ = "2.1 - hardcoded" #kmetadata.version("unoserver")
logger = logging.getLogger("unoserver")


logger = logging.getLogger("unoserver")

SFX_FILTER_IMPORT = 1
SFX_FILTER_EXPORT = 2
DOC_TYPES = {
    "com.sun.star.sheet.SpreadsheetDocument",
    "com.sun.star.text.TextDocument",
    "com.sun.star.presentation.PresentationDocument",
    "com.sun.star.drawing.DrawingDocument",
    "com.sun.star.sdb.DocumentDataSource",
    "com.sun.star.formula.FormulaProperties",
    "com.sun.star.script.BasicIDE",
    "com.sun.star.text.WebDocument",  # Supposedly deprecated? But still around.
}


def prop2dict(properties):
    return {p.Name: p.Value for p in properties}


def get_doc_type(doc):
    for t in DOC_TYPES:
        if doc.supportsService(t):
            return t

    # LibreOffice opened it, but it's not one of the known document types.
    # This really should only happen if a future version of LibreOffice starts
    # adding document types, which seems unlikely.
    raise RuntimeError(
        "The input document is of an unknown document type. This is probably a bug.\n"
        "Please create an issue at https://github.com/unoconv/unoserver."
    )


class UnoServer:
    def __init__(
        self,
        interface="127.0.0.1",
        port="2003",
        uno_interface="127.0.0.1",
        uno_port="2002",
        user_installation=None,
    ):
        self.interface = interface
        self.uno_interface = uno_interface
        self.port = port
        self.uno_port = uno_port
        self.user_installation = user_installation
        self.libreoffice_process = None
        self.xmlrcp_thread = None
        self.xmlrcp_server = None

    def start(self, executable="libreoffice"):
        logger.info(f"Starting unoserver {__version__}.")

        connection = (
            "socket,host=%s,port=%s,tcpNoDelay=1;urp;StarOffice.ComponentContext"
            % (self.uno_interface, self.uno_port)
        )

        # I think only --headless and --norestore are needed for
        # command line usage, but let's add everything to be safe.
        cmd = [
            executable,
            "--headless",
            "--invisible",
            "--nocrashreport",
            "--nodefault",
            "--nologo",
            "--nofirststartwizard",
            "--norestore",
            f"-env:UserInstallation={self.user_installation}",
            f"--accept={connection}",
        ]

        logger.info("Command: " + " ".join(cmd))
        self.libreoffice_process = subprocess.Popen(cmd)
        self.xmlrcp_thread = threading.Thread(None, self.serve)

        def signal_handler(signum, frame):
            logger.info("Sending signal to LibreOffice")
            try:
                self.libreoffice_process.send_signal(signum)
            except ProcessLookupError as e:
                # 3 means the process is already dead
                if e.errno != 3:
                    raise

            if self.xmlrcp_server is not None:
                self.xmlrcp_server.shutdown()

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        # Signal SIGHUP is available only in Unix systems
        if platform.system() != "Windows":
            signal.signal(signal.SIGHUP, signal_handler)

        self.xmlrcp_thread.start()
        return self.libreoffice_process

    def serve(self):
        # Create server
        with xmlrpc.server.SimpleXMLRPCServer(
            (self.interface, int(self.port)), allow_none=True
        ) as server:
            self.xmlrcp_server = server

            server.register_introspection_functions()

            @server.register_function
            def convert(
                inpath=None,
                indata=None,
                outpath=None,
                convert_to=None,
                filtername=None,
                filter_options=[],
                update_index=True,
                infiltername=None,
            ):
                if indata is not None:
                    indata = indata.data
                conv = UnoConverter(
                    interface=self.uno_interface, port=self.uno_port
                )
                result = conv.convert(
                    inpath,
                    indata,
                    outpath,
                    convert_to,
                    filtername,
                    filter_options,
                    update_index,
                    infiltername,
                )
                return result

            server.serve_forever()

    def stop(self):
        if self.libreoffice_process:
            self.libreoffice_process.terminate()
        if self.xmlrcp_server is not None:
            self.xmlrcp_server.shutdown()
        if self.xmlrcp_thread is not None:
            self.xmlrcp_thread.join()


def main():
    logging.basicConfig()
    logger.setLevel(logging.INFO)

    parser = argparse.ArgumentParser("unoserver")
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        help="Display version and exit.",
        version=f"{parser.prog} {__version__}",
    )
    parser.add_argument(
        "--interface",
        default="127.0.0.1",
        help="The interface used by the XMLRPC server",
    )
    parser.add_argument(
        "--uno-interface",
        default="127.0.0.1",
        help="The interface used by the Libreoffice UNO server",
    )
    parser.add_argument(
        "--port", default="2003", help="The port used by the XMLRPC server"
    )
    parser.add_argument(
        "--uno-port", default="2002", help="The port used by the Libreoffice UNO server"
    )
    parser.add_argument("--daemon", action="store_true", help="Deamonize the server")
    parser.add_argument(
        "--executable",
        default="libreoffice",
        help="The path to the LibreOffice executable",
    )
    parser.add_argument(
        "--user-installation",
        default=None,
        help="The path to the LibreOffice user profile",
    )
    parser.add_argument(
        "--libreoffice-pid-file",
        "-p",
        default=None,
        help="If set, unoserver will write the Libreoffice PID to this file. If started "
        "in daemon mode, the file will not be deleted when unoserver exits.",
    )
    args = parser.parse_args()

    if args.daemon:
        cmd = sys.argv
        cmd.remove("--daemon")
        proc = subprocess.Popen(cmd)
        return proc.pid

    with tempfile.TemporaryDirectory() as tmpuserdir:
        user_installation = Path(tmpuserdir).as_uri()

        if args.user_installation is not None:
            user_installation = Path(args.user_installation).as_uri()

        if args.uno_port == args.port:
            raise RuntimeError("--port and --uno-port must be different")

        server = UnoServer(
            args.interface,
            args.port,
            args.uno_interface,
            args.uno_port,
            user_installation,
        )

        # If it's daemonized, this returns the process.
        # It returns 0 of getting killed in a normal way.
        # Otherwise it returns 1 after the process exits.
        process = server.start(executable=args.executable)
        pid = process.pid

        logger.info(f"Server PID: {pid}")

        if args.libreoffice_pid_file:
            with open(args.libreoffice_pid_file, "wt") as upf:
                upf.write(f"{pid}")

        process.wait()

        if args.libreoffice_pid_file:
            # Remove the PID file
            os.unlink(args.libreoffice_pid_file)

        try:
            # Make sure it's really dead
            os.kill(pid, 0)
            # It was killed
            return 0
        except OSError as e:
            if e.errno == 3:
                # All good, it was already dead.
                return 0
            raise



def prop2dict(properties):
    return {p.Name: p.Value for p in properties}


def get_doc_type(doc):
    for t in DOC_TYPES:
        if doc.supportsService(t):
            return t

    # LibreOffice opened it, but it's not one of the known document types.
    # This really should only happen if a future version of LibreOffice starts
    # adding document types, which seems unlikely.
    raise RuntimeError(
        "The input document is of an unknown document type. This is probably a bug.\n"
        "Please create an issue at https://github.com/unoconv/unoserver."
    )


class OutputStream(unohelper.Base, XOutputStream):
    def __init__(self):
        self.buffer = io.BytesIO()

    def closeOutput(self):
        pass

    def writeBytes(self, seq):
        self.buffer.write(seq.value)


class UnoConverter:
    """The class that performs the conversion

    Don't use this directly, instead use the client.UnoConverter.
    """

    def __init__(self, interface="127.0.0.1", port="2002"):
        logger.info("Starting unoconverter.")

        self.local_context = uno.getComponentContext()
        self.resolver = self.local_context.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", self.local_context
        )
        self.context = self.resolver.resolve(
            f"uno:socket,host={interface},port={port};urp;StarOffice.ComponentContext"
        )
        self.service = self.context.ServiceManager
        self.desktop = self.service.createInstanceWithContext(
            "com.sun.star.frame.Desktop", self.context
        )
        self.filter_service = self.service.createInstanceWithContext(
            "com.sun.star.document.FilterFactory", self.context
        )
        self.type_service = self.service.createInstanceWithContext(
            "com.sun.star.document.TypeDetection", self.context
        )

    def find_filter(self, import_type, export_type):
        for export_filter in self.get_available_export_filters():
            if export_filter["DocumentService"] != import_type:
                continue
            if export_filter["Type"] != export_type:
                continue

            # There is only one possible filter per import and export type,
            # so the first one we find is correct
            return export_filter["Name"]

        # No filter found
        return None

    def get_available_import_filters(self):
        # List import filters. You can only search on module, iflags and eflags,
        # so the import and export types we have to test in a loop
        import_filters = self.filter_service.createSubSetEnumerationByQuery(
            "getSortedFilterList():iflags=1"
        )

        while import_filters.hasMoreElements():
            # Filter DocumentService here
            yield prop2dict(import_filters.nextElement())

    def get_available_export_filters(self):
        # List export filters. You can only search on module, iflags and eflags,
        # so the import and export types we have to test in a loop
        export_filters = self.filter_service.createSubSetEnumerationByQuery(
            "getSortedFilterList():iflags=2"
        )

        while export_filters.hasMoreElements():
            # Filter DocumentService here
            yield prop2dict(export_filters.nextElement())

    def get_filter_names(self, filters):
        names = {}
        for flt in filters:
            # Add all names and exstensions, etc in a mapping to the internal
            # Libreoffice name, so we can map it.
            # The actual name:
            names[flt["Name"]] = flt["Name"]
            # UserData sometimes has file extensions, etc.
            # Skip empty data, and those weird file paths, and "true"...
            for name in filter(
                lambda x: x and x != "true" and "." not in x, flt["UserData"]
            ):
                names[name] = flt["Name"]
        return names

    def convert(
        self,
        inpath=None,
        indata=None,
        outpath=None,
        convert_to=None,
        filtername=None,
        filter_options=[],
        update_index=True,
        infiltername=None,
    ):
        """Converts a file from one type to another

        inpath: A path (on the local hard disk) to a file to be converted.

        indata: A byte string containing the file content to be converted.

        outpath: A path (on the local hard disk) to store the result, or None, in which case
                 the content of the converted file will be returned as a byte string.

        convert_to: The extension of the desired file type, ie "pdf", "xlsx", etc.

        filtername: The name of the export filter to use for conversion. If None, it is auto-detected.

        filter_options: A list of output filter options as strings, in a "OptionName=Value" format.

        update_index: Updates the index before conversion

        infiltername: The name of the input filter, ie "writer8", "PowerPoint 3", etc.

        You must specify the inpath or the indata, and you must specify and outpath or a convert_to.
        """
        input_props = (PropertyValue(Name="ReadOnly", Value=True),)
        if infiltername:
            infilters = self.get_filter_names(self.get_available_import_filters())
            if infiltername in infilters:
                input_props += (
                    PropertyValue(Name="FilterName", Value=infilters[infiltername]),
                )
            else:
                raise ValueError(
                    f"There is no '{infiltername}' import filter. Available filters: {sorted(infilters.keys())}"
                )

        if inpath:
            # TODO: Verify that inpath exists and is openable, and that outdir exists, because uno's
            # exceptions are completely useless!

            if not Path(inpath).exists():
                raise RuntimeError(f"Path {inpath} does not exist.")

            # Load the document
            logger.info(f"Opening {inpath} for input")
            import_path = uno.systemPathToFileUrl(os.path.abspath(inpath))

        elif indata:
            # The document content is passed in as a byte string
            logger.info("Opening private:stream for input")
            old_stream = self.service.createInstanceWithContext(
                "com.sun.star.io.SequenceInputStream", self.context
            )
            old_stream.initialize((uno.ByteSequence(indata),))
            input_props += (PropertyValue(Name="InputStream", Value=old_stream),)
            import_path = "private:stream"

        document = self.desktop.loadComponentFromURL(
            import_path, "_default", 0, input_props
        )

        if document is None:
            # Could not load document, fail
            if not inpath:
                inpath = "<remote file>"
            if not infiltername:
                infiltername = "default"

            error = f"Could not load document {inpath} using the {infiltername} filter."
            logger.error(error)
            raise RuntimeError(error)

        if update_index:
            # Update document indexes
            for ii in range(2):
                # At first, update Table-of-Contents.
                # ToC grows, so page numbers grow too.
                # On second turn, update page numbers in ToC.
                try:
                    document.refresh()
                    indexes = document.getDocumentIndexes()
                except AttributeError:
                    # The document doesn't implement the XRefreshable and/or
                    # XDocumentIndexesSupplier interfaces
                    break
                else:
                    for i in range(0, indexes.getCount()):
                        indexes.getByIndex(i).update()

        # Now do the conversion
        try:
            # Figure out document type:
            import_type = get_doc_type(document)

            if outpath:
                export_path = uno.systemPathToFileUrl(os.path.abspath(outpath))
            else:
                export_path = "private:stream"

            # Figure out the output type:
            if convert_to:
                export_type = self.type_service.queryTypeByURL(
                    f"file:///dummy.{convert_to}"
                )
            else:
                export_type = self.type_service.queryTypeByURL(export_path)

            if not export_type:
                if convert_to:
                    extension = convert_to
                else:
                    extension = os.path.splitext(outpath)[-1]
                raise RuntimeError(
                    f"Unknown export file type, unknown extension '{extension}'"
                )

            if filtername is not None:
                available_filter_names = self.get_filter_names(
                    self.get_available_export_filters()
                )
                if filtername not in available_filter_names:
                    raise RuntimeError(
                        f"There is no '{filtername}' export-filter. Available filters: {sorted(available_filter_names)}"
                    )
            else:
                filtername = self.find_filter(import_type, export_type)
                if filtername is None:
                    raise RuntimeError(
                        f"Could not find an export filter from {import_type} to {export_type}"
                    )

            logger.info(f"Exporting to {outpath}")
            logger.info(
                f"Using {filtername} export filter from {infiltername} to {export_type}"
            )

            filter_data = []
            for option in filter_options:
                option_name, option_value = option.split("=", maxsplit=1)
                if option_value == "false":
                    option_value = False
                elif option_value == "true":
                    option_value = True
                elif option_value.isdecimal():
                    option_value = int(option_value)
                filter_data.append(PropertyValue(Name=option_name, Value=option_value))
            output_props = (
                PropertyValue(Name="FilterName", Value=filtername),
                PropertyValue(Name="Overwrite", Value=True),
            )
            if outpath is None:
                output_stream = OutputStream()
                output_props += (
                    PropertyValue(Name="OutputStream", Value=output_stream),
                )
            if filter_data:
                output_props += (
                    PropertyValue(
                        Name="FilterData",
                        Value=uno.Any(
                            "[]com.sun.star.beans.PropertyValue", tuple(filter_data)
                        ),
                    ),
                )
            document.storeToURL(export_path, output_props)

        finally:
            document.close(True)

        if outpath is None:
            return output_stream.buffer.getvalue()
        else:
            return None

if __name__ == "__main__":
    main()