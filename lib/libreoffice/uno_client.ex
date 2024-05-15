defmodule Libreoffice.UnoClient do
  use GenServer
  require Logger

  def command do
    # todo: pass into start_link
    python_path = Application.fetch_env!(:thumbs, :libreoffice_python_path)
    unoserver_path = Application.fetch_env!(:thumbs, :libreoffice_unoserver_path)

    "#{python_path} #{unoserver_path}"
  end

  defstruct [:erl_port]

  def child_spec(opts) do
    %{
      id: __MODULE__,
      start: {__MODULE__, :start_link, [opts ++ [name: __MODULE__]]},
      type: :worker,
      restart: :permanent,
      shutdown: 5000
    }
  end

  # GenServer API
  def start_link(args \\ [], opts \\ []) do
    GenServer.start_link(__MODULE__, args, opts)
  end

  def init(_args \\ []) do
    Process.flag(:trap_exit, true)

    erl_port = Port.open({:spawn, command()}, [:binary, :exit_status])
    Port.monitor(erl_port)

    {:ok, %__MODULE__{erl_port: erl_port}}
  end

  # This callback handles data incoming from the command's STDOUT
  def handle_info({port, {:data, text_line}}, %{port: port} = state) do
    IO.puts(String.trim(text_line))
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
    info("Terminating Unoserver, kill external process and close port. reason=#{inspect(reason)}")

    case Port.info(erl_port, :os_pid) do
      # Kill the process - for some reason process does not shut down
      {:os_pid, process_pid} ->
        info("Kill unoserver.py process os_pid=#{process_pid}")
        System.cmd("kill", ["#{process_pid}"])

      nil ->
        info("No OS process, nothing to kill")
    end

    Port.close(erl_port)
    :ok
  end

  def info(msg) do
    Logger.info("UnoServer: " <> msg)
  end
end
