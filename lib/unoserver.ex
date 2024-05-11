defmodule Unoserver do
  use GenServer
  require Logger

  def command do
    # todo: pass into start_link
    python_path = Application.fetch_env!(:thumbs, :libreoffice_python_path)
    bin_path = Application.fetch_env!(:thumbs, :libreoffice_bin_path)
    unoserver_path = Application.fetch_env!(:thumbs, :libreoffice_unoserver_path)

    "#{python_path} #{unoserver_path} --executable #{bin_path}"
  end

  # GenServer API
  def start_link(args \\ [], opts \\ []) do
    GenServer.start_link(__MODULE__, args, opts)
  end

  def init(_args \\ []) do
    Process.flag(:trap_exit, true)

    # Start the uno server (python lib) which spins up a soffice (libreoffice) instance
    # and accepts xmlrpc commands
    # This is faster than loading libreoffice each time
    port = Port.open({:spawn, command()}, [:binary, :exit_status])

    Port.monitor(port)

    {:ok, %{port: port} }
  end

  # This callback handles data incoming from the command's STDOUT
  def handle_info({port, {:data, text_line}}, %{port: port} = state) do
    Logger.info "Data: #{inspect text_line}"
    {:noreply, state}
  end

  # Port closed down for some reason
  def handle_info({_port, {:exit_status, status}}, state) do
    Logger.info "Port exit: :exit_status: #{status}"
    {:noreply, state}
  end

  def handle_info({:DOWN, _ref, :port, port, :normal}, state) do
    Logger.info "Handled :DOWN message from port: #{inspect port}"
    {:noreply, state}
  end

  def handle_info({:EXIT, _, :normal}, state) do
    Logger.info "Trap exit mate"
    {:stop, :shutdown, state}
  end

  def handle_info(msg, state) do
    Logger.info "Unhandled message: #{inspect msg}"
    {:noreply, state}
  end

  def terminate(_reason, %{port: port}) do
    Logger.info "Terminating Unoserver, kill external process and close port"
    {:os_pid, process_pid} = Port.info(port, :os_pid)
    # Kill the process - for some reason process does not shut down
    System.cmd("kill", ["#{process_pid}"])
    Port.close(port)
    :ok
  end
end
