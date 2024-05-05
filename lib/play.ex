defmodule Play do
  def run do
    # /Applications/LibreOffice.app/Contents/Resources/python -m unoserver.server --executable /Applications/LibreOffice.app/Contents/MacOS/soffice
    # {'inpath': '/Users/venkat/Downloads/StanfordTax-TOS-Revised.docx', 'indata': False, 'outpath': '/Users/venkat/Downloads/dude.pdf',
    # 'convert_to': 'pdf', 'filtername': None, 'filter_options': [], 'update_index': True, 'infiltername': None}

    opts = [
      in_path: "/Users/venkat/Downloads/StanfordTax-TOS-Revised.docx",
      in_data: nil,
      out_path: "/Users/venkat/Downloads/dude.pdf",
      convert_to: "pdf",
      filter_name: nil,
      filter_options: [],
      update_index: true,
      in_filter_name: nil
    ]

    params = for {_k, v} <- opts, do: v

    request_body = %XMLRPC.MethodCall{
      method_name: "convert",
      params: params
    }
    |> XMLRPC.encode!()


    Req.post!("http://127.0.0.1:2003", body: request_body)
  end
end
