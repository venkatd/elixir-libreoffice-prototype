defmodule ThumbsWeb.ConvertController do
  use ThumbsWeb, :controller

  def convert_to_pdf(conn, %{"files" => file_params}) do
    {:ok, filepath} = save_file(file_params)

    IO.puts("saved file to #{filepath}")

    {:ok, pdf_path} = Libreoffice.UnoClient.convert(Libreoffice.UnoClient, filepath, "pdf")

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
end
