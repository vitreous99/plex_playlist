# Interfacing with the Plex Sonic API

Once the LLM has provided a set of seed tracks or artists, the application should use Plex's sonic analysis to refine and expand the playlist. These features are available via the `plexapi.audio` module.

## Sonically similar discoveries

The `sonicallySimilar()` method is the primary tool for expanding a playlist based on acoustic properties. It can be called on an `Artist`, `Album`, or `Track` object.

```python
# Programmatic usage of sonic similarity
track = music_section.get("Song Title", artist="Artist Name")
# limit: max results, maxDistance: tighter similarity (0.0 to 1.0)
recommendations = track.sonicallySimilar(limit=50, maxDistance=0.20)
```

The `maxDistance` parameter controls similarity. For example, use `maxDistance=0.1` for "strictly similar" recommendations, or `maxDistance=0.4` for more varied, exploratory results.

## Programmatic "Sonic Adventures"

For transition-based prompts (e.g., "start with chill acoustic and end with high-energy rock"), use the `sonicAdventure()` method. It accepts a target track and returns a curated path that bridges the sonic gap between the source and destination, enabling narrative-style playlists that standard shuffle cannot provide.

```python
# Example (conceptual):
path = music_section.sonicAdventure(from_track=source_track, to_track=target_track)
```
