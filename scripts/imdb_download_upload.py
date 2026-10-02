import os
import requests
import boto3

from config import imdb_output_dir, s3_bucket_name

def download_imdb_data(urls, output_dir):
    for url in urls:
        filename = url.split("/")[-1]
        save_path = os.path.join(output_dir, filename)
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            f.write(response.content)

def upload_to_s3(local_path, bucket_name, s3_key):
    s3_client = boto3.client('s3')
    for filename in os.listdir(local_path):
        file_path = os.path.join(local_path, filename)
        s3_client.upload_file(file_path, bucket_name, f"{s3_key}/{filename}")

def cleanup(local_path):
    for filename in os.listdir(local_path):
         os.remove(os.path.join(local_path, filename))

def main():
    output_dir = imdb_output_dir()
    os.makedirs(output_dir, exist_ok=True)

    try:
        urls = ["https://datasets.imdbws.com/name.basics.tsv.gz", "https://datasets.imdbws.com/title.akas.tsv.gz", "https://datasets.imdbws.com/title.basics.tsv.gz",
                "https://datasets.imdbws.com/title.crew.tsv.gz", "https://datasets.imdbws.com/title.principals.tsv.gz", "https://datasets.imdbws.com/title.ratings.tsv.gz"]

        download_imdb_data(urls, output_dir)
        upload_to_s3(output_dir, s3_bucket_name(), "imdb")
    finally:
        cleanup(output_dir)

if __name__ == "__main__":
    main()
