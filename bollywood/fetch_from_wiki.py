from requests import Session
from bs4 import BeautifulSoup
import json
import os
import argparse
import sys

def get_hits_table(soup: BeautifulSoup):
    def is_table_headline(tag):
        hits_strings = ["box office", "box-office", "boxoffice", "grossing", "revenue"]
        if tag.get('class')==["mw-headline"]: 
            if any(s in tag.get_text().lower() for s in hits_strings):
                 return True
            else:
                next_p = tag.find_next("p")
                if next_p:
                    return any(s in next_p.get_text().lower() for s in hits_strings)
                else:
                    return False
        else:
            return False
    
    headline = soup.find(is_table_headline)
    if headline is None:
        raise ValueError('No headline found.')
    else:
        table = headline.find_next(lambda t: t.name == "table" and 5 <= len(t.find_all('tr')) <= 40)
        if table is None:
            raise ValueError("Couldn't find hits table with correct length")
        return table


def get_titles(table: BeautifulSoup):
    # Find all rows in the table.
    rows = table.find_all('tr')

    # Get the header row and find the index of the "Title" column.
    header_row = rows[0]
    headers = header_row.find_all('td') or header_row.find_all('th')  # Header could be in either 'td' or 'th' tags.

    # Find the index of the "Title" column (case-insensitive).
    title_index = None
    for i, header in enumerate(headers):
        if header.get_text().strip().lower() == 'title':
            title_index = i
            break

    if title_index is None:
        return None
    else:
        # Extract the title and href from the title column of each row.
        titles_and_links = []
        for row in rows[1:]:  # Skip the header row.
            columns = row.find_all(lambda tag: tag.name == 'td' or tag.name == 'th')
            if len(columns) > title_index:  # Ensure the row has enough columns.
                title_column = columns[title_index]  # The title column.
                
                # Title is linked. Hence find 'a' tag.
                title_tag = title_column.find('a')
                if title_tag:
                    title = title_tag.text
                    link = title_tag['href']
                    titles_and_links.append((title, link))

        return titles_and_links
    
def get_movie_info_from_soup(soup: str) -> str:
    paras = [p for p in soup.find_all('p') if len(p.get_text()) > 50]
    infobox = soup.find_all(class_="infobox")
    info_string = ""
    attributes = ["direct", "starring", "cast", "box office", "revenue", "music", "composed", "produce"]
    if len(infobox) > 0:
        infos = infobox[0].find_all(lambda tag: tag.name == "tr" and any([attr in tag.get_text().lower() for attr in attributes]))
        info_string = " \n ".join([info.get_text(",") for info in infos])
    return (paras, info_string) 

def process_movies(from_year: int, to_year: int):
    session = Session()
    movies = []
    for year in range(from_year, to_year+1): 
        try:
            list_url = "https://en.wikipedia.org/wiki/List_of_Hindi_films_of_{}".format(year)
            list_resp = session.get(list_url, timeout=10)
            list_soup = BeautifulSoup(list_resp.text, "html.parser")
            hits_table = get_hits_table(list_soup)
            titles = get_titles(hits_table)
            if titles:
                if (len(titles) > 10):
                    print("Warning: got {} titles for {}, only going to keep 10".format(len(titles), year))
                    titles = titles[:10]
                else:
                    print("Processing {} titles for {}".format(len(titles), year))
            else:
                print("No titles for {}!".format(year))
            #continue
            for (title, link) in titles:
                if not link.startswith("/wiki/"):
                    print("Skipping {}, {} because it doesn't start with /wiki/, year {}".format(title, link, year))
                    continue
                movie_url = "https://en.wikipedia.org{}".format(link)
                resp = session.get(movie_url, timeout=10)
                soup = BeautifulSoup(resp.text, "html.parser")
                (paras, infos) = get_movie_info_from_soup(soup)
                if len(paras) == 0 and len(infos) == 0:
                    print("No info for {}".format(movie_url))
                else:
                    movies.append(
                        {
                            "year": year,
                            "title": title,
                            "movie_url": movie_url,
                            "paras": paras,
                            "infobox": infos
                        }
                    )
        except ValueError as e:
            print("Got exception for {}: {}".format(year, e))
            continue
        sys.stdout.flush()
    return movies


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-year", type=int, default=1947)
    parser.add_argument("--to-year", type=int, default=2022)
    parser.add_argument("--output-file", type=str, required=True)
    args = parser.parse_args()

    if os.path.exists(args.output_file):
        print("File {} already exists, exiting".format(args.output_file))
        exit(0)

    movies = process_movies(args.from_year, args.to_year)

    # change paras to list of strings
    for movie in movies:
        movie["paras"] = [p.get_text() for p in movie["paras"]]
    with open(args.output_file, "w") as f:
        print("Writing {} movies to {}".format(len(movies), args.output_file))
        for movie in movies:
            f.write(json.dumps(movie) + "\n")
        print("Done writing")
