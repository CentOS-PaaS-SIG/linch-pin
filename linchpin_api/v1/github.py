import requests
import json


class GitHub:

    def __init__(self, url):
        self.url = url.strip(".git").strip("/")
        self.owner = self.url.split("/")[-2]
        self.repo = self.url.split("/")[-1].strip("/")
        self.api_url = "https://api.github.com/repos"

    def get_rq_url(self, directory):
        return self.api_url+"/"+self.owner+"/"+self.repo+"/contents/"+directory

    def list_files(self, directory):
        rq_url = self.get_rq_url(directory)
        rq = requests.get(rq_url)
        if (rq.ok):
            files = json.loads(rq.text or rq.content)
            return files

    def download_file(self, dest, directory, file_name):
        pass
