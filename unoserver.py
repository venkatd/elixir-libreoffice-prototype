import logging
import uno

from pathlib import Path
from com.sun.star.beans import PropertyValue
import argparse
import logging
import xmlrpc.server

logger = logging.getLogger("unoserver")

DOC_TYPES = {
    "com.sun.star.sheet.SpreadsheetDocument",
    "com.sun.star.text.TextDocument",
    "com.sun.star.presentation.PresentationDocument",
    "com.sun.star.drawing.DrawingDocument",
    "com.sun.star.sdb.DocumentDataSource",
    "com.sun.star.formula.FormulaProperties",
    "com.sun.star.script.BasicIDE",
    "com.sun.star.text.WebDocument",
}

def prop2dict(properties):
    return {p.Name: p.Value for p in properties}

def get_doc_type(doc):
    for t in DOC_TYPES:
        if doc.supportsService(t):
            return t
    raise RuntimeError(
        "The input document is of an unknown document type. This is probably a bug.\n"
        "Please create an issue at https://github.com/unoconv/unoserver."
    )

class UnoServer:
    def __init__(
        self,
        unoserver_host="127.0.0.1",
        unoserver_port="2003",
        soffice_host="127.0.0.1",
        soffice_port="2002",
    ):
        self.unoserver_host = unoserver_host
        self.unoserver_port = unoserver_port

        self.soffice_host = soffice_host
        self.soffice_port = soffice_port

        self.xmlrcp_server = None

    def serve(self):
        logger.info("serve")
        with xmlrpc.server.SimpleXMLRPCServer(
            (self.unoserver_host, int(self.unoserver_port)), allow_none=True
        ) as server:
            self.xmlrcp_server = server

            @server.register_function
            def convert(
                inpath=None,
                outpath=None,
                convert_to=None,
                filtername=None,
                filter_options=[],
                update_index=True,
            ):
                conv = UnoConverter(
                    soffice_host=self.soffice_host, soffice_port=self.soffice_port
                )

                logger.info("init conv")
                result = conv.convert(
                    inpath,
                    outpath,
                    convert_to,
                    filtername,
                    filter_options,
                    update_index
                )
                return result

            logger.info("server.start")
            server.serve_forever()

    def stop(self):
        if self.xmlrcp_server is not None:
            self.xmlrcp_server.shutdown()


class UnoConverter:
    def __init__(self, soffice_host, soffice_port):
        self.local_context = uno.getComponentContext()
        self.resolver = self.local_context.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", self.local_context
        )
        logger.info(f"uno:socket,host={soffice_host},port={soffice_port};urp;StarOffice.ComponentContext")
        self.context = self.resolver.resolve(
            f"uno:socket,host={soffice_host},port={soffice_port};urp;StarOffice.ComponentContext"
        )
        logger.info("STARTED!")
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
        logger.info("Started instances")

    def find_filter(self, import_type, export_type):
        for export_filter in self.get_available_export_filters():
            if export_filter["DocumentService"] != import_type:
                continue
            if export_filter["Type"] != export_type:
                continue
            return export_filter["Name"]
        return None

    def get_available_import_filters(self):
        import_filters = self.filter_service.createSubSetEnumerationByQuery(
            "getSortedFilterList():iflags=1"
        )
        while import_filters.hasMoreElements():
            yield prop2dict(import_filters.nextElement())

    def get_available_export_filters(self):
        export_filters = self.filter_service.createSubSetEnumerationByQuery(
            "getSortedFilterList():iflags=2"
        )
        while export_filters.hasMoreElements():
            yield prop2dict(export_filters.nextElement())

    def get_filter_names(self, filters):
        names = {}
        for flt in filters:
            names[flt["Name"]] = flt["Name"]
            for name in filter(
                lambda x: x and x != "true" and "." not in x, flt["UserData"]
            ):
                names[name] = flt["Name"]
        return names

    def convert(
        self,
        input_path=None,
        output_path=None,
        convert_to=None,
        filtername=None,
        filter_options=[],
        update_index=True,
    ):
        logger.info("Calling convert function with arguments:")
        logger.info(f"inpath: {input_path}")
        logger.info(f"outpath: {output_path}")
        logger.info(f"convert_to: {convert_to}")
        logger.info(f"filtername: {filtername}")
        logger.info(f"filter_options: {filter_options}")
        logger.info(f"update_index: {update_index}")

        input_props = (PropertyValue(Name="ReadOnly", Value=True),)

        if not Path(input_path).exists():
            raise RuntimeError(f"Path {input_path} does not exist.")

        logger.info(f"Opening document at {input_path}")

        document = self.desktop.loadComponentFromURL(
            "file://" + input_path, "_default", 0, input_props
        )

        if document is None:
            error = f"Could not load document {input_path} using the default filter."
            logger.error(error)
            raise RuntimeError(error)

        if update_index:
            for ii in range(2):
                try:
                    document.refresh()
                    indexes = document.getDocumentIndexes()
                except AttributeError:
                    break
                else:
                    for i in range(0, indexes.getCount()):
                        indexes.getByIndex(i).update()

        try:
            import_type = get_doc_type(document)

            export_type = self.type_service.queryTypeByURL(
                f"file:///dummy.{convert_to}"
            )
            if not export_type:
                raise RuntimeError(
                    f"Unknown export file type, unknown extension '{convert_to}'"
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
                
            logger.info(f"Exporting to {output_path}")
            logger.info(
                f"Using {filtername} export filter to {export_type}"
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
            if filter_data:
                output_props += (
                    PropertyValue(
                        Name="FilterData",
                        Value=uno.Any(
                            "[]com.sun.star.beans.PropertyValue", tuple(filter_data)
                        ),
                    ),
                )
            document.storeToURL("file://" + output_path, output_props)
        finally:
            document.close(True)

        return None
        
def main():
    logging.basicConfig()
    logger.setLevel(logging.INFO)

    parser = argparse.ArgumentParser("unoserver")
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
    args = parser.parse_args()

    server = UnoServer(
        args.interface,
        args.port,
        args.uno_interface,
        args.uno_port,
    )

    server.serve()

if __name__ == "__main__":
    main()
