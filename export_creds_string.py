import yaml
import json
import os
import sys

def main():
    config_path = "flattradecred.yaml"
    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found. Are you in the right directory?")
        sys.exit(1)
        
    try:
        with open(config_path, "r") as f:
            cred = yaml.load(f, Loader=yaml.FullLoader)
            
        json_creds = {
            "user_id": cred.get("user_id", cred.get("user", "")),
            "password": cred.get("password", cred.get("pwd", "")),
            "factor2": cred.get("factor2", ""),
            "api_key": cred.get("apikey", cred.get("api_key", "")),
            "api_secret": cred.get("apisecret", cred.get("api_secret", ""))
        }
        
        json_string = json.dumps(json_creds)
        print("\n--- COPY THE STRING BELOW ---\n")
        print(json_string)
        print("\n-----------------------------\n")
        print("You can now safely copy this string and paste it into the UI's 'PASTE CREDS' button.")
        
    except Exception as e:
        print(f"Error parsing credentials: {e}")

if __name__ == "__main__":
    main()
