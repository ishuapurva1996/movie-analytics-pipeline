import requests
import json
import pandas as pd

from config import tmdb_genres_csv, tmdb_headers


def main():
    url = "https://api.themoviedb.org/3/genre/movie/list?language=en"
    headers = tmdb_headers()

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    data = json.loads(response.text)
    genre_data = data['genres']

    genre_id = []
    genre_name = []
    for genre in genre_data:
        genre_id.append(genre['id'])
        genre_name.append(genre['name'])

    d = {'id': genre_id, 'name': genre_name}
    df = pd.DataFrame(d)

    output_path = tmdb_genres_csv()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)


if __name__ == "__main__":
    main()
