defmodule Libreoffice.SOfficeServer do
  use GenServer
  require Logger

  @moduledoc """
  A module to run a LibreOffice server
  """

  defstruct [:erl_port]

  @default_soffice_host "127.0.0.1"
  @default_soffice_port 2002

  def child_spec(opts) do
    %{
      id: __MODULE__,
      start: {__MODULE__, :start_link, [opts ++ [name: __MODULE__]]},
      type: :worker,
      restart: :permanent,
      shutdown: 5000
    }
  end

  def start_link(args \\ [], opts \\ []) do
    GenServer.start_link(__MODULE__, args, opts)
  end

  def init(opts) do
    port = Keyword.get(opts, :port, @default_soffice_port)
    host = Keyword.get(opts, :host, @default_soffice_host)

    bin_path = Application.fetch_env!(:thumbs, :libreoffice_bin_path)
    user_installation_dir = System.tmp_dir!() |> Path.join("libreoffice_user")
    System.cmd("mkdir", ["-p", user_installation_dir])

    cmd =
      [
        bin_path,
        "--headless",
        "--invisible",
        "--nocrashreport",
        "--nodefault",
        "--nologo",
        "--nofirststartwizard",
        "--norestore",
        "-env:UserInstallation=file://#{user_installation_dir}",
        "--accept=\"socket,host=#{host},port=#{port},tcpNoDelay=1;urp;StarOffice.ComponentContext\""
      ]

    Process.flag(:trap_exit, true)

    # Logger.info(Enum.join(cmd, " "))
    # Start the uno server (python lib) which spins up a soffice (libreoffice) instance
    # and accepts xmlrpc commands
    # This is faster than loading libreoffice each time
    erl_port =
      Port.open({:spawn, Enum.join(cmd, " ")}, [:binary, :exit_status]) |> IO.inspect(label: :yea)

    Port.monitor(erl_port)

    {:ok, %__MODULE__{erl_port: erl_port}}
  end

  # This callback handles data incoming from the command's STDOUT
  def handle_info({_port, {:data, text_line}}, state) do
    info("Data: #{inspect(text_line)}")
    {:noreply, state}
  end

  # Port closed down for some reason
  def handle_info({_port, {:exit_status, status}}, state) do
    info("Port exit: :exit_status: #{status}")
    {:noreply, state}
  end

  def handle_info({:DOWN, _ref, :port, port, :normal}, state) do
    info("Handled :DOWN message from port: #{inspect(port)}")
    {:noreply, state}
  end

  def handle_info({:EXIT, _, :normal}, state) do
    info("Trap exit mate")
    {:stop, :shutdown, state}
  end

  def handle_info(msg, state) do
    info("Unhandled message: #{inspect(msg)}")
    {:noreply, state}
  end

  def terminate(reason, %{erl_port: erl_port}) do
    info("Terminating soffice, kill external process and close port. reason=#{inspect(reason)}")

    case Port.info(erl_port, :os_pid) do
      # Kill the process - for some reason process does not shut down
      {:os_pid, process_pid} ->
        info("terminating #{process_pid}")
        System.cmd("kill", ["#{process_pid}"])

      nil ->
        info("No OS process, nothing to kill")
    end

    Port.close(erl_port)
    :ok
  end

  def info(msg) do
    Logger.info("Libreoffice.Server: " <> msg)
  end
end
