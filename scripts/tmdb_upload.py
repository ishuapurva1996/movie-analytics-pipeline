import boto3
import os

from config import s3_bucket_name, tmdb_output_dir

def upload_to_s3(local_path, bucket_name, s3_key):
    s3_client = boto3.client('s3')
    for filename in os.listdir(local_path):
        file_path = os.path.join(local_path, filename)
        s3_client.upload_file(file_path, bucket_name, f"{s3_key}/{filename}")

def cleanup(local_path):
    for filename in os.listdir(local_path):
        os.remove(os.path.join(local_path, filename))

def main():
    output_dir = tmdb_output_dir()
    os.makedirs(output_dir, exist_ok=True)

    upload_to_s3(output_dir, s3_bucket_name(), "tmdb")
    cleanup(output_dir)

if __name__ == "__main__":
    main()
