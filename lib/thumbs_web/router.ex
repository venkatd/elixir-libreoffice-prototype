defmodule ThumbsWeb.Router do
  use ThumbsWeb, :router

  pipeline :browser do
    plug :accepts, ["html"]
    plug :fetch_session
    plug :put_root_layout, html: {ThumbsWeb.Layouts, :root}
    plug :protect_from_forgery
    plug :put_secure_browser_headers
  end

  pipeline :api do
    plug :accepts, ["json"]
  end

  scope "/api", ThumbsWeb do
    pipe_through :api

    post "/convert/pdf", ConvertController, :convert_to_pdf
  end
end
