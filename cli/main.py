import argparse
import json
import logging
import os
import requests
import subprocess
from typing import Optional, Dict

# Constants
API_URL = "https://api.brankopetric.com/kubew"
CREDENTIALS_PATH = os.path.expanduser("~/.kubew/credentials.json")

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



def parse_arguments():
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="KubeWhisper CLI Tool")
    parser.add_argument(
        "query_text", type=str, help="The query text to send.", nargs="?"
    )
    parser.add_argument(
        "-a",
        "--auto-complete",
        action="store_true",
        help="Auto-complete the suggested command.",
    )
    parser.add_argument(
        "--register", help="Register with your email and password.", nargs=2, metavar=("email", "password")
    )
    parser.add_argument(
        "--login", help="Authenticate with your email and password.", nargs=2, metavar=("email", "password")
    )
    parser.add_argument(
        "--history", action="store_true", help="Retrieve query history."
    )
    parser.add_argument(
        "--verify", help="Verification code.", nargs=2, metavar=("email", "code")
    )
    return parser.parse_args()


def main():
    """Main function to handle CLI input and call appropriate API methods."""
    args = parse_arguments()
    api_client = KubeWhisperAPI()

    try:
        if args.register:
            email, password = args.register
            api_client.register_user(email, password)

        elif args.login:
            email, password = args.login
            api_client.authenticate_user(email, password)
        
        elif args.verify:
            email, code = args.verify
            api_client.verify_user(email, code)

        elif args.history:
            history = api_client.get_history()
            if history:
                print("Query History:")
                for entry in history.get("entries", []):
                    print(f"Query: {entry['query']}\nResponse: {entry['response']}\n")

        elif args.query_text:
            result = api_client.get_command_response(args.query_text)
            if result:
                print(f"KubeWhisper: {result}")
                if args.auto_complete:
                    print("Executing command...")
                    subprocess.run(result, shell=True, check=True)

        else:
            print("No command specified.")

    except KubeWhisperException as e:
        logger.error(f"Error: {e.message}")

if __name__ == "__main__":
    main()
