defmodule Play do
  def run do
    opts = [
      in_path: "/tmp/test.doc",
      in_data: nil,
      out_path: "/tmp/test.doc.pdf",
      convert_to: "pdf",
      filter_name: nil,
      filter_options: [],
      update_index: true,
      in_filter_name: nil
    ]

    params = for {_k, v} <- opts, do: v

    request_body =
      %XMLRPC.MethodCall{
        method_name: "convert",
        params: params
      }
      |> XMLRPC.encode!()

    Req.post!("http://127.0.0.1:2003", body: request_body)
  end
end
