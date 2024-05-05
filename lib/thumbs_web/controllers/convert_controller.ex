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
    case System.cmd(Application.fetch_env!(:thumbs, :libreoffice_bin_path), [
           "--headless",
           "--convert-to",
           "pdf",
           filepath,
           "--outdir",
           System.tmp_dir(),
           filepath
         ]) do
      {convert_output, 0} -> {:ok, parse_output_path(convert_output)}
    end
  end

  def parse_output_path(soffice_output) do
    [_, path_and_msg | _rest] = String.split(soffice_output, " -> ")
    [output_path | _rest] = String.split(path_and_msg, " using filter :")
    output_path
  end
end
