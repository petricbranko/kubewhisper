import argparse
import json
import logging
import os
import requests
import subprocess
from typing import Optional, Dict, List
import webbrowser
import sys
import signal
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich import print as rprint

# Constants
API_URL = "https://api.kubewhisper.com/kubew"
CREDENTIALS_PATH = os.path.expanduser("~/.kubew/credentials.json")
CONTEXT_PATH = os.path.expanduser("~/.kubew/context.json")
should_exit = False

# ASCII Banner
KUBEWHISPER_BANNER = """
▗▖ ▗▖▗▖ ▗▖▗▄▄▖ ▗▄▄▄▖▗▖ ▗▖▗▖ ▗▖▗▄▄▄▖ ▗▄▄▖▗▄▄▖ ▗▄▄▄▖▗▄▄▖
▐▌▗▞▘▐▌ ▐▌▐▌ ▐▌▐▌   ▐▌ ▐▌▐▌ ▐▌  █  ▐▌   ▐▌ ▐▌▐▌   ▐▌ ▐▌
▐▛▚▖ ▐▌ ▐▌▐▛▀▚▖▐▛▀▀▘▐▌ ▐▌▐▛▀▜▌  █   ▝▀▚▖▐▛▀▘ ▐▛▀▀▘▐▛▀▚▖
▐▌ ▐▌▝▚▄▞▘▐▙▄▞▘▐▙▄▄▖▐▙█▟▌▐▌ ▐▌▗▄█▄▖▗▄▄▞▘▐▌   ▐▙▄▄▖▐▌ ▐▌
"""

# Funny Kubernetes-themed loading messages
LOADING_VERBS = [
    "Kubeing",
    "Whispering to pods",
    "DevOpsing",
    "Orchestrating containers",
    "Helmifying",
    "Kubectling",
    "Namespacing",
    "Deploying thoughts",
    "Scaling brain cells",
    "Rolling out ideas",
    "Podding around",
    "Yaml-ing",
    "Containering",
    "Clustering neurons",
    "Ingressing wisdom"
]

# Funny Kubernetes-themed execution messages
EXECUTION_VERBS = [
    "Kubectling away",
    "Unleashing the pods",
    "Spinning up containers",
    "Orchestrating chaos",
    "Deploying magic",
    "Scaling to infinity",
    "Rolling out the red carpet",
    "Commanding the cluster",
    "Whispering to the API server",
    "Helming the ship",
    "Namespacing like a boss",
    "Yaml-wrangling",
    "Service meshing",
    "Config-mapping the future",
    "CronJobbing around"
]

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kubew_cli")


class KubeWhisperException(Exception):
    """Base exception class for KubeWhisper API errors."""
    pass


class AuthenticationError(KubeWhisperException):
    """Raised when there is an authentication error with the API."""
    def __init__(self, message="Authentication required or token expired."):
        self.message = message
        super().__init__(self.message)


class RequestError(KubeWhisperException):
    """Raised for errors related to API requests."""
    def __init__(self, status_code: int, message="API request error"):
        self.status_code = status_code
        self.message = f"{message} (Status code: {status_code})"
        super().__init__(self.message)


class ParsingError(KubeWhisperException):
    """Raised when there is an error parsing the API response."""
    def __init__(self, message="Error parsing the response body."):
        self.message = message
        super().__init__(self.message)


class MissingTokenError(KubeWhisperException):
    """Raised when an id token is required but missing."""
    def __init__(self, message="ID token is missing; please register or authenticate."):
        self.message = message
        super().__init__(self.message)


class KubeWhisperAPI:
    """Class to encapsulate API operations for the CLI."""

    def __init__(self):
        self.api_url = API_URL
        self.token = None  # Token will be loaded when needed

    def _load_token(self) -> Optional[str]:
        """Load id token from credentials file if it exists."""
        if os.path.exists(CREDENTIALS_PATH):
            with open(CREDENTIALS_PATH, "r") as file:
                credentials = json.load(file)
                return credentials.get("id_token")
        return None

    def _get_username(self) -> Optional[str]:
        """Load username from credentials file if it exists."""
        if os.path.exists(CREDENTIALS_PATH):
            with open(CREDENTIALS_PATH, "r") as file:
                credentials = json.load(file)
                return credentials.get("username")
        return None

    def _save_user_data(self, username: str):
        """Save or update the username in the credentials file without overwriting other fields."""
        data = {}
        
        # Load existing data if the file exists
        if os.path.exists(CREDENTIALS_PATH):
            with open(CREDENTIALS_PATH, "r") as file:
                try:
                    data = json.load(file)
                except json.JSONDecodeError:
                    logger.error("Failed to decode JSON; reinitializing credentials file.")

        # Update or add the username
        data["username"] = username
        os.makedirs(os.path.dirname(CREDENTIALS_PATH), exist_ok=True)

        # Write updated data back to the file
        with open(CREDENTIALS_PATH, "w") as file:
            json.dump(data, file)

    def _save_token(self, token: str):
        """Save or update the id token in the credentials file without overwriting other fields."""
        data = {}
        
        # Load existing data if the file exists
        if os.path.exists(CREDENTIALS_PATH):
            with open(CREDENTIALS_PATH, "r") as file:
                try:
                    data = json.load(file)
                except json.JSONDecodeError:
                    logger.error("Failed to decode JSON; reinitializing credentials file.")

        # Update or add the id token
        data["id_token"] = token
        os.makedirs(os.path.dirname(CREDENTIALS_PATH), exist_ok=True)

        # Write updated data back to the file
        with open(CREDENTIALS_PATH, "w") as file:
            json.dump(data, file)

    def _get_token(self) -> str:
        """Ensure the token is loaded and available."""
        if not self.token:
            self.token = self._load_token()
        if not self.token:
            raise MissingTokenError("Token not found; please register or authenticate.")
        return self.token

    def format_payload(self, path: str, data: Dict) -> Dict:
        """Format the payload with specified path and JSON-encoded body."""
        return {
            "path": path,
            "body": json.dumps(data)
        }

    def post_request(self, endpoint: str, data: Dict, requires_auth=True) -> Optional[Dict]:
        """Generic POST request to the KubeWhisper API with token authentication."""
        headers = {"Authorization": f"Bearer {self._get_token()}"} if requires_auth else {}

        # Format payload using the helper function
        payload = self.format_payload(f"/{endpoint}", data)

        url = f"{self.api_url}/{endpoint}"
        try:
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 401:
                raise AuthenticationError("Token expired or missing; please re-authenticate.")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise RequestError(response.status_code, f"Request to {endpoint} failed: {e}")
        except requests.exceptions.RequestException as e:
            raise RequestError(-1, f"Network error during request to {endpoint}: {e}")

    def register_user(self, email: str, password: str) -> Optional[str]:
        """Register a user and save the id token."""
        payload = {"username": email, "password": password, "email": email}
        response = self.post_request("register", payload, requires_auth=False)

        # Safely parse the response and extract token
        if response and response.get("statusCode") == 200:
            logger.info("Registration successful; Check your email for verification code.")
            return
        logger.error("Registration failed.")
        return None

    def authenticate_user(self, email: str, password: str) -> Optional[str]:
        """Authenticate a user and refresh the id token."""
        payload = {"username": email, "password": password}
        response = self.post_request("login", payload, requires_auth=False)

        # Safely parse the response and extract token
        if response and response.get("statusCode") == 200:
            body = json.loads(response.get("body", "{}"))
            token = body.get("IdToken")
            if token:
                self._save_token(token)
                self._save_user_data(email)
                self.token = token
                logger.info("Authentication successful; token saved.")
            return token
        logger.error("Authentication failed; token not received.")
        return None

    def verify_user(self, email: str, code: str) -> Optional[str]:
        """Verify a user with the verification code."""
        payload = {"username": email, "code": code}
        response = self.post_request("verify", payload, requires_auth=False)
        
        # Safely parse the response and extract token
        if response and response.get("statusCode") == 200:
            body = json.loads(response.get("body", "{}"))
            token = body.get("IdToken")
            if token:
                self._save_token(token)
                self._save_user_data(email)
                self.token = token
                logger.info("Verification successful; token saved.")
            return token
        logger.error("Verification failed.")
        return None

    def get_command_response(self, query: str) -> Optional[str]:
        """Send a query to the API and return the extracted command."""
        email = self._get_username()
        payload = {"query": query, "user_id": email}
        response_json = self.post_request("query", payload)
        response_body = response_json.get("body")

        if response_body:
            try:
                parsed_body = json.loads(response_body)
                full_response = parsed_body.get("response", "")
                command = full_response.replace("Response: ", "").strip()
                return command
            except json.JSONDecodeError:
                raise ParsingError("Failed to parse the response body.")
        else:
            raise ParsingError("No 'body' field found in the response.")

    def get_history(self) -> Optional[Dict]:
        """Retrieve the user's query history."""
        email = self._get_username()
        payload = {"user_id": email}
        return self.post_request("history", payload)

    def save_token(self, token: str) -> None:
        """Save the provided token."""
        self._save_token(token)
        logger.info("Token saved successfully. You can now use KubeWhisper.")


class KubeContextManager:
    """Manage Kubernetes context for queries."""

    def __init__(self):
        self.context_path = CONTEXT_PATH
        self.console = Console()

    def save_context(self, context: Dict) -> None:
        """Save Kubernetes context to file."""
        os.makedirs(os.path.dirname(self.context_path), exist_ok=True)
        with open(self.context_path, "w") as file:
            json.dump(context, file, indent=2)

    def load_context(self) -> Optional[Dict]:
        """Load saved Kubernetes context."""
        if os.path.exists(self.context_path):
            with open(self.context_path, "r") as file:
                return json.load(file)
        return None

    def get_current_k8s_context(self) -> Optional[str]:
        """Get current kubectl context."""
        try:
            result = subprocess.run(
                ["kubectl", "config", "current-context"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def get_k8s_contexts(self) -> List[str]:
        """Get all available kubectl contexts."""
        try:
            result = subprocess.run(
                ["kubectl", "config", "get-contexts", "-o", "name"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip().split("\n")
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []

    def switch_context(self, context_name: str) -> bool:
        """Switch kubectl context."""
        try:
            subprocess.run(
                ["kubectl", "config", "use-context", context_name],
                capture_output=True,
                text=True,
                check=True
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def display_context_info(self) -> None:
        """Display current context information."""
        current = self.get_current_k8s_context()
        saved = self.load_context()

        table = Table(title="Kubernetes Context")
        table.add_column("Type", style="cyan")
        table.add_column("Value", style="green")

        if current:
            table.add_row("Current kubectl context", current)
        else:
            table.add_row("Current kubectl context", "Not configured", style="yellow")

        if saved:
            table.add_row("Saved context", saved.get("context", "None"))
            if saved.get("namespace"):
                table.add_row("Default namespace", saved.get("namespace"))

        self.console.print(table)



def parse_arguments():
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="KubeWhisper CLI Tool - Kubernetes command generator",
        epilog="""
Examples:
  kubewhisper                                    # Start interactive mode (default)
  kubewhisper -i                                 # Start interactive mode explicitly
  kubewhisper "show all pods in prod?"           # Quick query (use quotes for special chars)
  kubewhisper show all pods in prod              # Quick query without special characters
  kubewhisper --login                            # Open login page
  kubewhisper --token YOUR_TOKEN                 # Save authentication token

Note: When using queries with special characters like ?, *, or spaces outside
interactive mode, wrap your query in quotes to prevent shell interpretation.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "query_text", type=str, help="The query text to send (use quotes for special chars like ?)", nargs="*"
    )
    parser.add_argument(
        "-a",
        "--auto-complete",
        action="store_true",
        help="Auto-complete the suggested command.",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open the login page in browser"
    )
    parser.add_argument(
        "--token",
        type=str,
        help="Save authentication token"
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Retrieve query history."
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Start interactive shell mode"
    )
    return parser.parse_args()

def signal_handler(sig, frame):
    """Handle Ctrl+C by setting global exit flag"""
    global should_exit
    should_exit = True
    print("\nPress Ctrl+C again or type 'exit' to quit")

def display_help(console: Console) -> None:
    """Display help information in rich format."""
    help_text = """
# KubeWhisper Interactive Mode - Commands

## Basic Commands
- `help` - Show this help message
- `exit`, `quit` - Exit the interactive shell
- `clear` - Clear the screen

## Slash Commands (type / for autocomplete)
- `/context` - Show current Kubernetes context
- `/contexts` - List all available Kubernetes contexts
- `/switch <context>` - Switch to a different context
- `/history` - Show query history
- `/login` - Open login page in browser
- `/token <token>` - Save authentication token
- `/status` - Show authentication status

## Query Mode
Simply type your natural language query to get kubectl commands:
- Example: "show all pods in default namespace"
- Example: "get services in production"
- Example: "describe deployment my-app"

Commands will be displayed for approval before execution.
    """
    console.print(Panel(Markdown(help_text), title="Help", border_style="cyan"))


class RotatingStatus:
    """A status context manager that rotates messages at intervals."""
    def __init__(self, console: Console, messages: List[str], interval: float = 1.0,
                 interrupt_key: str = None, interrupt_message: str = None):
        self.console = console
        self.messages = messages
        self.interval = interval
        self.interrupt_key = interrupt_key
        self.interrupt_message = interrupt_message
        self.stop_event = None
        self.interrupted = False
        self.thread = None
        self.current_status = None

    def __enter__(self):
        import threading
        import itertools

        self.stop_event = threading.Event()
        message_cycle = itertools.cycle(self.messages)

        def rotate():
            while not self.stop_event.is_set():
                if self.current_status:
                    msg = f"[bold cyan]{next(message_cycle)}..."
                    if self.interrupt_message:
                        msg += f" [dim yellow]{self.interrupt_message}[/dim yellow]"
                    self.current_status.update(msg)
                self.stop_event.wait(self.interval)

        self.current_status = self.console.status("[bold cyan]Loading...", spinner="dots")
        self.current_status.__enter__()

        self.thread = threading.Thread(target=rotate, daemon=True)
        self.thread.start()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.stop_event:
            self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=0.5)
        if self.current_status:
            self.current_status.__exit__(exc_type, exc_val, exc_tb)
        return False


def approve_command(console: Console, command: str) -> bool:
    """Ask user to approve command execution."""
    console.print("\n[bold yellow]Generated Command:[/bold yellow]")
    syntax = Syntax(command, "bash", theme="monokai", line_numbers=False)
    console.print(Panel(syntax, border_style="yellow"))

    from prompt_toolkit import prompt
    from prompt_toolkit.validation import Validator, ValidationError

    class YesNoValidator(Validator):
        def validate(self, document):
            text = document.text.lower()
            if text not in ['y', 'n', 'yes', 'no', '']:
                raise ValidationError(message="Please enter 'y' or 'n'")

    response = prompt(
        "Execute this command? [Y/n]: ",
        validator=YesNoValidator(),
        default='y'
    ).lower()

    return response in ['y', 'yes', '']


def interactive_shell(kubewhisper):
    """Run an interactive shell for KubeWhisper."""
    from prompt_toolkit import PromptSession
    from prompt_toolkit.styles import Style
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.completion import WordCompleter

    console = Console()
    context_manager = KubeContextManager()

    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)

    style = Style.from_dict({
        'prompt': 'ansicyan bold',
    })

    # Slash command completer
    slash_commands = {
        '/context': 'Show current Kubernetes context',
        '/contexts': 'List all available Kubernetes contexts',
        '/switch': 'Switch to a different context',
        '/history': 'Show query history',
        '/login': 'Open login page in browser',
        '/token': 'Save authentication token',
        '/status': 'Show authentication status',
    }

    command_completer = WordCompleter(
        list(slash_commands.keys()),
        meta_dict=slash_commands,
        ignore_case=True,
        sentence=True
    )

    # History file
    history_file = os.path.expanduser("~/.kubew/history")
    os.makedirs(os.path.dirname(history_file), exist_ok=True)

    session = PromptSession(
        history=FileHistory(history_file),
        auto_suggest=AutoSuggestFromHistory(),
        completer=command_completer,
        complete_while_typing=True
    )

    # Display banner
    console.print(KUBEWHISPER_BANNER, style="bold cyan")
    console.print(Panel.fit(
        "[bold white]Interactive Kubernetes Assistant[/bold white]\n"
        "Type [cyan]help[/cyan] for commands or just ask questions in natural language",
        border_style="cyan"
    ))

    # Show current context
    current_ctx = context_manager.get_current_k8s_context()
    if current_ctx:
        console.print(f"\n[dim]Current context: {current_ctx}[/dim]\n")

    global should_exit

    while True:
        try:
            if should_exit:
                console.print("\n[bold cyan]Goodbye! Thanks for using KubeWhisper.[/bold cyan]")
                sys.exit(0)

            user_input = session.prompt("kubewhisper> ", style=style)

            if not user_input.strip():
                continue

            # Handle exit commands
            if user_input.lower() in ['exit', 'quit']:
                console.print("[bold cyan]Goodbye! Thanks for using KubeWhisper.[/bold cyan]")
                break

            # Handle help command
            if user_input.lower() == 'help':
                display_help(console)
                continue

            # Handle clear command
            if user_input.lower() == 'clear':
                os.system('clear' if os.name == 'posix' else 'cls')
                console.print(KUBEWHISPER_BANNER, style="bold cyan")
                continue

            # Handle context commands
            if user_input.lower() == '/context':
                context_manager.display_context_info()
                continue

            if user_input.lower() == '/contexts':
                contexts = context_manager.get_k8s_contexts()
                current = context_manager.get_current_k8s_context()

                table = Table(title="Available Kubernetes Contexts")
                table.add_column("Context", style="cyan")
                table.add_column("Current", style="green")

                for ctx in contexts:
                    is_current = "✓" if ctx == current else ""
                    table.add_row(ctx, is_current)

                console.print(table)
                continue

            if user_input.lower().startswith('/switch '):
                context_name = user_input[8:].strip()
                if context_manager.switch_context(context_name):
                    console.print(f"[green]✓ Switched to context: {context_name}[/green]")
                else:
                    console.print(f"[red]✗ Failed to switch context to: {context_name}[/red]")
                continue

            if user_input.lower() == '/history':
                try:
                    history_response = kubewhisper.get_history()
                    if history_response and history_response.get("statusCode") == 200:
                        history_entries = json.loads(history_response.get("body", "[]"))

                        table = Table(title="Query History")
                        table.add_column("Query", style="cyan", no_wrap=False)
                        table.add_column("Timestamp", style="yellow")

                        for entry in history_entries[-10:]:  # Last 10 entries
                            table.add_row(entry['query'], entry['timestamp'])

                        console.print(table)
                    else:
                        console.print("[yellow]No history available[/yellow]")
                except Exception as e:
                    console.print(f"[red]Error fetching history: {str(e)}[/red]")
                continue

            if user_input.lower() == '/login':
                login_url = "https://kubewhisper.com/login"
                webbrowser.open(login_url)
                console.print("[green]Browser opened to KubeWhisper login page.[/green]")
                console.print("[cyan]After logging in, copy the token and run: /token <your-token>[/cyan]")
                continue

            if user_input.lower().startswith('/token '):
                token = user_input[7:].strip()
                if token:
                    kubewhisper.save_token(token)
                    # Reload the token into the current instance
                    kubewhisper.token = token
                    console.print("[green]✓ Successfully logged in. You can now use KubeWhisper CLI.[/green]")
                else:
                    console.print("[red]✗ Please provide a token: /token <your-token>[/red]")
                continue

            if user_input.lower() == '/status':
                username = kubewhisper._get_username()
                token = kubewhisper._load_token()

                table = Table(title="Authentication Status")
                table.add_column("Field", style="cyan")
                table.add_column("Value", style="green")

                if username:
                    table.add_row("Username", username)
                else:
                    table.add_row("Username", "Not logged in", style="yellow")

                if token:
                    table.add_row("Token", "✓ Configured", style="green")
                else:
                    table.add_row("Token", "✗ Not configured", style="red")

                console.print(table)

                if not token:
                    console.print("\n[yellow]To login, run: /login[/yellow]")
                continue

            # Send query to KubeWhisper
            try:
                import threading
                import queue

                # Queue to check for interrupt
                interrupt_queue = queue.Queue()
                ai_stopped = threading.Event()

                def get_response():
                    try:
                        result = kubewhisper.get_command_response(user_input)
                        if not ai_stopped.is_set():
                            interrupt_queue.put(('response', result))
                    except Exception as e:
                        if not ai_stopped.is_set():
                            interrupt_queue.put(('error', e))

                def check_interrupt():
                    import sys
                    import select
                    while not ai_stopped.is_set():
                        # Check if 'x' or 'X' is pressed
                        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                            char = sys.stdin.read(1)
                            if char.lower() == 'x':
                                ai_stopped.set()
                                interrupt_queue.put(('interrupted', None))
                                break

                # Start API call in thread
                api_thread = threading.Thread(target=get_response, daemon=True)
                api_thread.start()

                # Show rotating status with interrupt hint
                with RotatingStatus(console, LOADING_VERBS, interval=1.0,
                                  interrupt_message="(Press X to cancel)"):
                    # Wait for response or interrupt
                    while api_thread.is_alive():
                        try:
                            result = interrupt_queue.get(timeout=0.1)
                            break
                        except queue.Empty:
                            continue
                    else:
                        # Thread finished, get result
                        try:
                            result = interrupt_queue.get(timeout=0.1)
                        except queue.Empty:
                            result = ('error', Exception("No response"))

                ai_stopped.set()

                # Handle result
                if result[0] == 'interrupted':
                    console.print("\n[yellow]⚠ AI response cancelled by user[/yellow]\n")
                elif result[0] == 'error':
                    raise result[1]
                elif result[0] == 'response':
                    response = result[1]

                    if response:
                        # Ask for approval before execution
                        if approve_command(console, response):
                            import random
                            import itertools
                            import select
                            import sys
                            import termios
                            import tty
                            from rich.live import Live
                            from rich.text import Text

                            # Create rotating execution status
                            execution_stopped = threading.Event()
                            exec_cycle = itertools.cycle(EXECUTION_VERBS)
                            command_stop_requested = threading.Event()

                            def check_stop_key():
                                """Check for 'C' key press to stop execution"""
                                old_settings = termios.tcgetattr(sys.stdin)
                                try:
                                    tty.setcbreak(sys.stdin.fileno())
                                    while not execution_stopped.is_set():
                                        if sys.stdin in select.select([sys.stdin], [], [], 0.1)[0]:
                                            char = sys.stdin.read(1)
                                            if char.lower() == 'c':
                                                command_stop_requested.set()
                                                break
                                finally:
                                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

                            # Start key listener thread
                            key_thread = threading.Thread(target=check_stop_key, daemon=True)
                            key_thread.start()

                            try:
                                # Use Popen to allow interruption
                                process = subprocess.Popen(
                                    response,
                                    shell=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True
                                )

                                # Show rotating execution status with Live
                                with Live(console=console, refresh_per_second=4) as live:
                                    # Poll process while checking for stop request
                                    while process.poll() is None:
                                        if command_stop_requested.is_set():
                                            process.terminate()
                                            try:
                                                process.wait(timeout=2)
                                            except subprocess.TimeoutExpired:
                                                process.kill()
                                            break

                                        # Update status with rotating message
                                        status_text = Text()
                                        status_text.append(next(exec_cycle) + "...", style="bold green")
                                        status_text.append(" (Press C to stop)", style="dim yellow")
                                        live.update(status_text)

                                        import time
                                        time.sleep(1.0)

                                execution_stopped.set()

                                if command_stop_requested.is_set():
                                    console.print("\n[yellow]⚠ Command execution stopped by user[/yellow]\n")
                                else:
                                    stdout, stderr = process.communicate()

                                    console.print()  # Add newline after status
                                    if process.returncode == 0:
                                        if stdout:
                                            console.print(stdout)
                                        if stderr:
                                            console.print(f"[yellow]{stderr}[/yellow]")
                                        console.print("[green]✓ Command executed successfully[/green]\n")
                                    else:
                                        console.print(f"[red]✗ Command failed with exit code {process.returncode}[/red]")
                                        if stdout:
                                            console.print(stdout)
                                        if stderr:
                                            console.print(f"[red]{stderr}[/red]")
                                        console.print()
                            finally:
                                execution_stopped.set()
                        else:
                            console.print("[yellow]Command execution cancelled[/yellow]\n")
                    else:
                        console.print("[yellow]No response received[/yellow]\n")
            except Exception as e:
                console.print(f"[red]Error: {str(e)}[/red]\n")

        except KeyboardInterrupt:
            if should_exit:
                console.print("\n[bold cyan]Goodbye! Thanks for using KubeWhisper.[/bold cyan]")
                sys.exit(0)
            should_exit = True
            console.print("\n[yellow]Press Ctrl+C again or type 'exit' to quit[/yellow]")
            continue
        except EOFError:
            console.print("\n[bold cyan]Goodbye! Thanks for using KubeWhisper.[/bold cyan]")
            break

def main():
    """Main function to handle CLI input and call appropriate API methods."""
    args = parse_arguments()
    api_client = KubeWhisperAPI()

    try:
        if args.login:
            # Open the login page in the default browser
            login_url = "https://kubewhisper.com/login"
            webbrowser.open(login_url)
            print("Browser opened to KubeWhisper login page.")
            print("After logging in, copy the token and run: kubewhisper --token <your-token>")
            sys.exit(0)

        if args.token:
            # Save the provided token
            api_client.save_token(args.token)
            print("Successfully logged in. You can now use KubeWhisper CLI.")
            sys.exit(0)
        
        if args.history:
            history_response = api_client.get_history()
            if history_response and history_response.get("statusCode") == 200:
                try:
                    history_entries = json.loads(history_response.get("body", "[]"))
                    print("Query History:")
                    for entry in history_entries:
                        print(f"Query: {entry['query']}\nUser ID: {entry['user_id']}\nTimestamp: {entry['timestamp']}\n")
                except json.JSONDecodeError:
                    logger.error("Failed to decode the history response.")
            else:
                print("No history available or an error occurred.")

        elif args.query_text:
            # Join all arguments as query text (no quotes needed)
            query = " ".join(args.query_text)

            # Show rotating loading verbs while waiting
            console = Console()
            with RotatingStatus(console, LOADING_VERBS, interval=1.0):
                result = api_client.get_command_response(query)

            if result:
                console.print(f"[bold cyan]KubeWhisper:[/bold cyan] {result}")
                if args.auto_complete:
                    console.print("[green]Executing command...[/green]")
                    subprocess.run(result, shell=True, check=True)

        elif args.interactive:
            interactive_shell(api_client)
            return

        else:
            # If no command specified, open interactive mode
            interactive_shell(api_client)
            return

    except KubeWhisperException as e:
        logger.error(f"Error: {e.message}")

if __name__ == "__main__":
    main()
