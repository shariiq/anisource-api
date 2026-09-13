"""Benchmark script comparing BeautifulSoup (html.parser), BeautifulSoup (lxml), and selectolax."""

from __future__ import annotations

import timeit

from bs4 import BeautifulSoup
from selectolax.parser import HTMLParser

FIXTURES = {
    "AniWaves Listing": """
    <div class="ani items">
      <div class="item">
        <a class="name" href="/watch/frieren-beyond-journeys-end.12345/ep-1" data-jp="葬送のフリーレン">Frieren</a>
        <div class="poster"><img data-src="https://static.example.com/poster.jpg"></div>
      </div>
      <div class="item">
        <a class="name" href="/watch/jujutsu-kaisen-2nd-season.67890/ep-23" data-jp="呪術廻戦">Jujutsu Kaisen</a>
        <div class="poster"><img src="https://static.example.com/poster2.jpg"></div>
      </div>
      <div class="item">
        <a class="name" href="/watch/one-piece.11111/ep-1100" data-jp="ワンピース">One Piece</a>
        <div class="poster"><img data-src="https://static.example.com/poster3.jpg"></div>
      </div>
    </div>
    <nav><ul class="pagination"><li class="active">1</li><li><a href="/page/2">2</a></li></ul></nav>
    """
    * 10,
    "Anikoto Details": """
    <h2 class="title" data-jp="葬送のフリーレン">Frieren</h2>
    <div id="watch-main" data-id="internal-999"></div>
    <img class="thumbnail" src="https://img.example/frieren.jpg">
    <div class="bmeta">
      <div class="meta">
        <div>Genres: <span><a>Fantasy</a><a>Drama</a><a>Adventure</a></span></div>
        <div>Studios: <span><a>Madhouse</a></span></div>
        <div>Status: <span>Finished Airing</span></div>
        <div>MAL: <span>9.35</span></div>
      </div>
    </div>
    <div class="synopsis"><div class="content">An elf mage reflects on her journey after the hero's party disbanded.</div></div>
    <div class="names font-italic">Sousou no Frieren; Beyond Journey's End; Frieren: Remnants of the Past</div>
    """
    * 10,
    "AnimeNoSub Details": """
    <h1 class="entry-title">Sousou no Frieren</h1>
    <div class="thumb"><img src="https://img.example/frieren.jpg"></div>
    <div class="info-content">
      <div class="genxed"><a>Fantasy</a><a>Drama</a><a>Magic</a></div>
      <div class="spe">
        <span><b>Status:</b> Completed</span>
        <span><b>Studio:</b> <a>Madhouse</a></span>
        <span><b>Fansub:</b> <a>SubsPlease</a></span>
        <span><b>Type:</b> TV</span>
        <span><b>Duration:</b> 24 min</span>
      </div>
    </div>
    <div class="entry-content" itemprop="description">Detailed description text for the anime series goes here.</div>
    <div class="alter">Frieren: Beyond Journey's End</div>
    """
    * 10,
    "Server Fragment": """
    <div class="servers">
      <div class="type" data-type="sub"><label>Sub</label>
        <ul>
          <li data-link-id="srv-1" class="active">Server 1 - Vidstream</li>
          <li data-link-id="srv-2">Server 2 - MegaCloud</li>
        </ul>
      </div>
      <div class="type" data-type="dub"><label>Dub</label>
        <ul>
          <li data-link-id="srv-3">Server 3 - StreamWish</li>
        </ul>
      </div>
    </div>
    """
    * 20,
    "Extractor Page (Gogo/Vidstream)": """
    <html>
      <head><title>Watch Episode 1 Online</title></head>
      <body class="container-12345">
        <div class="wrapper container-67890">
          <div class="videocontent videocontent-54321">
            <script data-value="U2FsdGVkX1+vupppZDm16W1e..."></script>
          </div>
        </div>
      </body>
    </html>
    """
    * 20,
}


def bench_bs4_html_parser(html: str) -> None:
    soup = BeautifulSoup(html, "html.parser")
    _ = soup.find_all("a")


def bench_bs4_lxml(html: str) -> None:
    soup = BeautifulSoup(html, "lxml")
    _ = soup.find_all("a")


def bench_selectolax(html: str) -> None:
    tree = HTMLParser(html)
    _ = tree.css("a")


def run_benchmarks(iterations: int = 500) -> None:
    print(f"Running HTML Parser Benchmark ({iterations} iterations per fixture)...\n")
    print(
        f"{'Fixture':<35} | {'bs4 (html.parser)':<18} | {'bs4 (lxml)':<14} | {'selectolax':<14} | {'Speedup (vs html.parser)'}"
    )
    print("-" * 120)

    for name, html in FIXTURES.items():
        t_html_parser = timeit.timeit(
            lambda html=html: bench_bs4_html_parser(html), number=iterations
        )
        t_lxml = timeit.timeit(lambda html=html: bench_bs4_lxml(html), number=iterations)
        t_selectolax = timeit.timeit(lambda html=html: bench_selectolax(html), number=iterations)

        speedup_selectolax = t_html_parser / t_selectolax if t_selectolax > 0 else 0
        print(
            f"{name:<35} | {t_html_parser * 1000:>14.2f} ms | {t_lxml * 1000:>10.2f} ms | {t_selectolax * 1000:>10.2f} ms | {speedup_selectolax:>6.2f}x faster (via selectolax)"
        )


if __name__ == "__main__":
    run_benchmarks()
