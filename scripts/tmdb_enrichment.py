import requests
import json
import pandas as pd
import time

from config import tmdb_details_csv, tmdb_headers, tmdb_now_playing_csv


REQUEST_TIMEOUT_SECONDS = 30
MAX_REQUEST_ATTEMPTS = 3
RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}


def extract_movieDetails_nowPlaying(url, headers):
        for attempt in range(MAX_REQUEST_ATTEMPTS):
            try:
                response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
                response.raise_for_status()
            except requests.HTTPError:
                if response.status_code not in RETRYABLE_HTTP_STATUSES or attempt == MAX_REQUEST_ATTEMPTS - 1:
                    raise
            except (requests.Timeout, requests.ConnectionError):
                if attempt == MAX_REQUEST_ATTEMPTS - 1:
                    raise
            else:
                break

            time.sleep(2 ** attempt)

        data = response.json()

        movie_details = {'id':data['id'], 
                          'imdb_id':data.get('imdb_id'),
                          'title': data['title'],
                          'budget': data['budget'],
                          'revenue': data['revenue'],
                          'release_date': data['release_date'],
                          'runtime': data['runtime'],
                          'status': data['status'],
                          'original_language': data['original_language'],
                          'origin_country': json.dumps(data.get('origin_country', [])),
                          'production_countries': json.dumps(data.get('production_countries', [])),
                          'production_companies': json.dumps(data.get('production_companies', [])),
                          'genres': json.dumps(data.get('genres', [])),
                          'vote_average': data['vote_average'],
                          'vote_count': data['vote_count'],
                          'poster_path': data.get('poster_path')
                          }
        return(movie_details)


def main():
        headers = tmdb_headers()
        
        csvFile = pd.read_csv(tmdb_now_playing_csv())

        movie_ids = csvFile['id'].unique()
        nowPlaying_details = []

        for movie_id in movie_ids:
            url = f'https://api.themoviedb.org/3/movie/{movie_id}?language=en-US'
            movie_details = extract_movieDetails_nowPlaying(url, headers)
            nowPlaying_details.append(movie_details)
            time.sleep(0.05)


        
        df = pd.DataFrame(nowPlaying_details)

        output_path = tmdb_details_csv()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)

if __name__ == "__main__":
        main()
