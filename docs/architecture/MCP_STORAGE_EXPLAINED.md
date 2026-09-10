# How MCP Stores the Taxonomy

MCP itself does not store anything — it is just the communication layer. The taxonomy is stored by regular Python code, in memory, as a graph object. MCP gives agents a way to call functions on that object over a network connection.

---

## What holds the data at each level

**The FASB XML file — stored on disk**

When `TaxonomyGraph()` is first created it downloads the FASB US-GAAP reference linkbase XML from FASB's servers and saves it to a local cache file. This only happens once. Every subsequent run reads from the cache instead of downloading again.

**The graph object — stored in RAM**

When the MCP server starts, it runs `graph = TaxonomyGraph()`. This reads the XML, parses every concept and every relationship, and builds an in-memory graph — essentially a Python dictionary of nodes and edges. This object lives in the server process's RAM for as long as the server is running.

```python
{
  "us-gaap:InventoryNet": {
      "label":    "Inventory, Net",
      "parent":   "us-gaap:Inventories",
      "citations": ["ASC 330-10-35-1"],
      "children": [...]
  },
  "us-gaap:AccountsReceivableNetCurrent": { ... },
  ...
}
```

Every agent call — `get_citation`, `validate_citation` — reads from this same object. Nothing is re-parsed between calls.

**Agent findings — stored in the MCP server's state dict**

When an agent calls `store_finding()`, the server appends that finding to a simple Python dict keyed by the audit item's ID:

```python
_state = {}   # lives in the server process

def store_finding(item_id, agent_id, finding):
    _state.setdefault(item_id, {})[agent_id] = finding
```

When the Judge calls `get_evidence(item_id)`, it gets back everything stored under that key — the Stage 0 result, the Auditor's finding, the Defender's finding. This is the shared state that makes the agents feel like they are communicating, even though they never talk to each other directly.

---

## The simple summary

```
Disk:  FASB XML file       (downloaded once, cached forever)
RAM:   TaxonomyGraph object (loaded at server startup, shared across all calls)
RAM:   _state dict          (agent findings written here, read by Judge)
```

When the server process stops, RAM is cleared. The disk cache stays. Next time you start the server, it reads from disk and rebuilds the graph in RAM — takes a few seconds.

---

*MCP_STORAGE_EXPLAINED.md · irvin/edgar-mapper branch · SFU CS Capstone · July 2026*
