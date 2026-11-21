"""Corpus refinery: from the raw lex.uz cache to a clean, dated, masked, leak-checked training corpus.

Design: docs/research/corpus_refinery.md. Stages are plain functions; `pilot.py` runs them end to end on a sample.
Only the cache is read: no network call is made anywhere in this package.
"""
