defmodule Thumbs.Release do
  @moduledoc """
  Used for executing DB release tasks when run in production without Mix
  installed.
  """
  @app :thumbs

  def migrate do
    load_app()
  end

  def rollback() do
    load_app()
  end

  defp load_app do
    Application.load(@app)
  end
end
