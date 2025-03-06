# gh_store/tools/canonical_snapshot.py

import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import os
from loguru import logger

from gh_store.core.exceptions import GitHubStoreError
from gh_store.tools.canonicalize import CanonicalStore


def create_canonical_snapshot(
    token: str | None = None,
    repo: str | None = None,
    output: str = "canonical_snapshot.json",
    config: str | None = None,
) -> None:
    """
    Create a full snapshot of all objects in the store, using the canonicalization
    machinery to merge updates across aliases.
    
    Args:
        token: GitHub token (optional, falls back to GITHUB_TOKEN env var)
        repo: GitHub repository (optional, falls back to GITHUB_REPOSITORY env var)
        output: Path to write output (defaults to canonical_snapshot.json)
        config: Path to config file (optional)
    """
    try:
        # Initialize CanonicalStore which has the virtual merge functionality
        token = token or os.environ["GITHUB_TOKEN"]
        repo = repo or os.environ["GITHUB_REPOSITORY"]
        config_path = Path(config) if config else None
        
        canonical_store = CanonicalStore(token=token, repo=repo, config_path=config_path)
        
        # Create snapshot data structure
        snapshot_data = {
            "snapshot_time": datetime.now(ZoneInfo("UTC")).isoformat(),
            "repository": repo,
            "objects": {},
            "relationships": {
                "aliases": {}
            }
        }
        
        # Find all aliases first
        aliases = canonical_store.find_aliases()
        logger.info(f"Found {len(aliases)} alias relationships")
        snapshot_data["relationships"]["aliases"] = aliases
        
        # Get all canonical objects (not aliases)
        # First, get all objects
        all_objects = canonical_store.list_all()
        logger.info(f"Found {len(all_objects)} total objects")
        
        # Track processed canonical IDs to avoid duplication
        processed_canonical_ids = set()
        
        # Process each object with virtual merge
        for obj_id, obj in all_objects.items():
            # Skip if we've already processed this as a canonical ID
            if obj_id in processed_canonical_ids:
                continue
                
            # Resolve to canonical ID
            canonical_id = canonical_store.resolve_canonical_object_id(obj_id)
            
            # Skip aliases - we'll process them through their canonical objects
            if canonical_id != obj_id:
                logger.info(f"Skipping alias {obj_id} -> {canonical_id}")
                continue
                
            # Mark this canonical ID as processed
            processed_canonical_ids.add(canonical_id)
            
            # Process with virtual merge to get the fully merged object
            try:
                merged_obj = canonical_store.process_with_virtual_merge(canonical_id)
                
                # Add to snapshot
                snapshot_data["objects"][canonical_id] = {
                    "data": merged_obj.data,
                    "meta": {
                        "created_at": merged_obj.meta.created_at.isoformat(),
                        "updated_at": merged_obj.meta.updated_at.isoformat(),
                        "version": merged_obj.meta.version
                    }
                }
                logger.info(f"Added canonical object {canonical_id} to snapshot")
                
            except Exception as e:
                logger.error(f"Error processing object {canonical_id}: {e}")
        
        # Write to file
        output_path = Path(output)
        output_path.write_text(json.dumps(snapshot_data, indent=2))
        logger.info(f"Canonical snapshot written to {output_path}")
        logger.info(f"Captured {len(snapshot_data['objects'])} canonical objects with {len(aliases)} aliases")
        
    except GitHubStoreError as e:
        logger.error(f"Failed to create canonical snapshot: {e}")
        raise SystemExit(1)
    except Exception as e:
        logger.exception("Unexpected error occurred")
        raise SystemExit(1)
