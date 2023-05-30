import openai
import os
import argparse
import json
import sys
import logging

def load_api_key():
    try:
        return os.environ["OPENAI_API_KEY"]
    except KeyError:
        print("Please set the OPENAI_API_KEY environment variable.")
        sys.exit(1)

def read_file(file_path):
    try:
        with open(file_path, "r") as file:
            return file.readlines()
    except IOError:
        logging.error(f"Error reading file: {file_path}")
        return None
    
def write_file(file_path, mode, data):
    try:
        with open(file_path, mode) as file:
            file.write(data)
            file.flush()
    except IOError:
        logging.error(f"Error writing to file: {file_path}")
        return False
    return True
    
def get_extracted_movie_object(movie: dict) -> dict:
    to_write = movie['ai_response']
    to_write['title'] = movie['title']
    to_write['year'] = movie['year']
    to_write['movie_url'] = movie['movie_url']
    return to_write

def make_movie_id(movie: dict) -> str:
    return str(movie['title']) + ":" + str(movie['year'])

prompt_prefix = """Process the following movie information and return json. 
Keys of the json should be 'plot', 'revenue', 'genres',
'cast', 'director', and 'female-led'. 
'plot' is a one sentence plot summary.
'genres' is an array of strings.
'revenue' is the box office revenue, a currency number with units. 
'cast' is an array of dicts with keys 'name' and 'gender'. 
'director' is a dict with keys 'name' and 'gender'. 
'female-led' is a boolean that is true if the plot of the movie
is primarily female led. E.g. "boy falls in love with girl" is not female led. 
"girl goes on a journey to discover her true self" is female led. 
Remove double quotes from the values to ensure well-formatted json.
----------
Movie info
---------- """
prompt_suffix = """----------
            JSON:----------"""

def query_davinci003(movie_info: str, max_tokens: int = 1000) -> str:
    response = openai.Completion.create(
        engine="davinci-003",
        prompt="\n".join([prompt_prefix, movie_info, prompt_suffix]),
        max_tokens=max_tokens,
        temperature=0,
    )
    return response.choices[0].text.strip()

def query_gpt3_5(movie_info: str, max_tokens: int = 1000) -> str:
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages = [
            {"role": "system", "content": prompt_prefix},
            {"role": "user", "content": movie_info.strip()},
        ],
        max_tokens=max_tokens,
        temperature=0,
    )
    return response['choices'][0]['message']['content'].strip()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", type=str, required=True)
    # add boolean flag to use gpt3.5
    parser.add_argument("--use-gpt3-5", action="store_true")
    parser.add_argument("--num-lines-to-read", type=int, required=True)
    parser.add_argument("--log-file", type=str, required=True)
    parser.add_argument("--output-file", type=str, required=True)
    args = parser.parse_args()

    logging.basicConfig(filename=args.log_file, level=logging.INFO)

    openai.api_key = load_api_key()

    movies_to_skip = set()
    out_file_mode = "a"
    if os.path.exists(args.output_file):
        user_input = input(
                        "File {} already exists. ".format(args.output_file) +
                        "Skip existing movies (answering 'no' will overwrite the existing file)?"
                    ).lower()
        if user_input not in ["n", "no"]:
            print("Ok, reading file {} to get movies to skip".format(args.output_file))
            with open(args.output_file, "r") as f:
                for line in f.readlines():
                    movie = json.loads(line)
                    movies_to_skip.add(make_movie_id(movie))
            print("Read {} movies to skip".format(len(movies_to_skip)))
            cont = input("Continue?").lower()
            if cont not in ["y", "yes"]:
                print("Exiting")
                exit(0)
        else:
            print("Ok, overwriting file {}".format(args.output_file))
            out_file_mode = "w"

    sys.stdout.flush()

    lines = read_file(args.input_file)
    if lines is None:
        sys.exit(1)
    lines = lines[:args.num_lines_to_read]
    movies = [json.loads(line) for line in lines]
    for movie in movies:
        if make_movie_id(movie) in movies_to_skip:
            logging.info("Skipping {}".format(movie['title']))
            continue
        
        max_paras_info = "\n".join(movie['paras'][:2])
        infobox = movie['infobox']
        if len(max_paras_info) > 1000:
            logging.info("Warning: truncating paras for {} from {} down to 1000".format(movie['title'], len(max_paras_info)))
            max_paras_info = max_paras_info[:1000]
        if len(infobox) > 500:
            logging.info("Warning: truncating infobox for {} from {} down to 500".format(movie['title'], len(infobox)))
            infobox = infobox[:500] 
        movie_info = "\n".join([max_paras_info, infobox])

        try:
            if args.use_gpt3_5:
                response_text = query_gpt3_5(movie_info)
            else:
                response_text = query_davinci003(movie_info)
            removed_text = response_text[:response_text.find("{")]
            if len(removed_text) > 0:
                logging.info("Removed text before first brace for movie {}: {}".format(movie['title'], removed_text))
            response_text = response_text[response_text.find("{"):]
        except Exception as e:
            logging.error("Got exception from OpenAI {}: {}".format(movie['title'], e))
            continue
        
        try:
            json_response = json.loads(response_text)
            movie['ai_response'] = json_response
            to_write = get_extracted_movie_object(movie)
            success = write_file(args.output_file, out_file_mode, json.dumps(to_write) + "\n")
            if not success:
                break
        except Exception as e:
            logging.exception("Exception parsing json response for movie {}: {}".format(
                movie['title'], response_text))
            break

        logging.info("Processed {}".format(movie['title']))



