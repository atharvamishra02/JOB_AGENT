import paramiko
import time
import sys
import os

from dotenv import load_dotenv
load_dotenv()

sys.stdout.reconfigure(encoding='utf-8')

host = os.getenv("DEPLOY_HOST", "")
user = os.getenv("DEPLOY_USER", "root")
password = os.getenv("DEPLOY_PASS", "")

if not host or not password:
    print("ERROR: Set DEPLOY_HOST and DEPLOY_PASS in your .env file.")
    sys.exit(1)

print("Connecting to server...")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=password)

print("Connected! Finding deployment directory...")
stdin, stdout, stderr = ssh.exec_command("find / -maxdepth 3 -name docker-compose.yml -path '*/job_agent/*'")
path = stdout.read().decode().strip()
if not path:
    # default fallback
    deploy_dir = "/root/job_agent"
    ssh.exec_command(f"mkdir -p {deploy_dir}")
else:
    deploy_dir = path.split('/docker-compose.yml')[0]

print(f"Target directory is: {deploy_dir}")

print("Uploading deploy_new.zip...")
for attempt in range(3):
    try:
        sftp = ssh.open_sftp()
        sftp.put("deploy_new.zip", f"{deploy_dir}/deploy_new.zip")
        sftp.close()
        break
    except Exception as e:
        print(f"SFTP failed: {e}. Retrying...")
        time.sleep(2)

print("Extracting and building...")
commands = [
    f"cd {deploy_dir}",
    "unzip -o deploy_new.zip",
    "docker compose down",
    "docker compose build",
    "docker compose up -d"
]
command_str = " && ".join(commands)

stdin, stdout, stderr = ssh.exec_command(command_str)
for line in iter(stdout.readline, ""):
    print(line, end="")
for line in iter(stderr.readline, ""):
    print(line, end="")

print("Deployment complete!")
ssh.close()
