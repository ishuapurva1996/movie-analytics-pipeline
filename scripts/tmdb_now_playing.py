import requests
import json
import pandas as pd
from datetime import date

from config import tmdb_headers, tmdb_now_playing_csv



def extract_movie_now_playing(headers, region):

    movies = []
    page = 1
    while True:
        url = "https://api.themoviedb.org/3/movie/now_playing"
        params = {
            "language": "en-US",
            "page": page,
            "region": region
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = json.loads(response.text)
        movies.extend(data['results'])
        
        
        if page >= data['total_pages']:
            break
        page += 1

    for m in movies:
        m['region'] = region
        m["snapshot_date"] = date.today().isoformat()
    
    return movies
    
    
    
def main():

    reg_movies = []
    headers = tmdb_headers()

    regions = ["US", "IN"]
    for region in regions:
        movies = extract_movie_now_playing(headers, region)
        reg_movies.extend(movies)


    id = []
    title = []
    release_date = []
    vote_average = []
    vote_count = []
    genre_ids = []
    overview = []
    poster_path= []
    popularity = []
    region = []
    snapshot_date = []
    for mov in reg_movies:
        id.append(mov['id'])
        title.append(mov['title'])
        release_date.append(mov['release_date'])
        vote_average.append(mov['vote_average'])
        vote_count.append(mov['vote_count'])
        genre_ids.append(mov['genre_ids'])
        overview.append(mov['overview'])
        poster_path.append(mov['poster_path'])
        popularity.append(mov['popularity'])
        region.append(mov['region'])
        snapshot_date.append(mov['snapshot_date'])

    d = {'id':id, 'title':title, 'release_date':release_date, 'vote_average':vote_average, 'vote_count':vote_count, 'genre_ids':genre_ids, 'overview':overview, 'poster_path':poster_path, 'popularity':popularity, 'region':region, 'snapshot_date': snapshot_date}
    df = pd.DataFrame(d)

    
  

    output_path = tmdb_now_playing_csv()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

        
    

if __name__ == "__main__":
    main()
