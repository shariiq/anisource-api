"""Anime Extensions REST API.

A high-performance, asynchronous REST API service exposing anime scrapers,
episode indexers, server resolvers, and video extractors.
"""

from .app import create_app

__version__ = "0.2.0"
__all__ = ["create_app", "__version__"]
