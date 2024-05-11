defmodule ThumbsWeb.ConvertController do
  use ThumbsWeb, :controller

  def convert_to_pdf(conn, %{"files" => file_params}) do
    {:ok, filepath} = save_file(file_params)

    {:ok, pdf_path} = convert_file_to_pdf(filepath)

    conn
    |> put_resp_content_type("application/pdf")
    |> send_file(200, pdf_path)
  end

  defp save_file(file_params) do
    upload = file_params.path
    target_path = Path.join(System.tmp_dir(), file_params.filename)
    case File.cp(upload, target_path) do
      :ok -> {:ok, target_path}
      {:error, error} -> {:error, error}
    end
  end

  defp convert_file_to_pdf(filepath) do
    out_path = Path.join(System.tmp_dir(), Path.basename(filepath) <> ".pdf")
    opts = [
      in_path: filepath,
      in_data: nil,
      out_path: out_path,
      convert_to: "pdf",
      filter_name: nil,
      filter_options: [],
      update_index: true,
      in_filter_name: nil
    ]

    request_body = %XMLRPC.MethodCall{
      method_name: "convert",
      params: Keyword.values(opts)
    }
    |> XMLRPC.encode!()


    Req.post!("http://127.0.0.1:2003", body: request_body)

    {:ok, out_path}
  end

  def parse_output_path(soffice_output) do
    [_, path_and_msg | _rest] = String.split(soffice_output, " -> ")
    [output_path | _rest] = String.split(path_and_msg, " using filter :")
    output_path
  end
end
