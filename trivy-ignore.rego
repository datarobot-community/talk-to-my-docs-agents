package trivy

import data.lib.trivy

default ignore := false

# litellm CVE-2026-35030 (CRITICAL), CVE-2026-35029 (HIGH), GHSA-69x8-hrgq-fjj8 (HIGH)
# Fixed in litellm>=1.83.0, but that version requires openai>=2 which is a breaking
# change (openai v2 = Responses API). web and agent_retrieval_agent are pinned to
# openai<2 until an openai v2 migration is completed. infra is already on >=1.83.0.
ignore {
    input.PkgName == "litellm"
    input.VulnerabilityID == "CVE-2026-35030"
}

ignore {
    input.PkgName == "litellm"
    input.VulnerabilityID == "CVE-2026-35029"
}

ignore {
    input.PkgName == "litellm"
    input.VulnerabilityID == "GHSA-69x8-hrgq-fjj8"
}

# litellm CVE-2026-49468 (CRITICAL) — Authentication Bypass via Host Header Injection.
# The flaw is in the LiteLLM *proxy server* auth layer (litellm/proxy/auth/auth_utils.py,
# advisory GHSA-4xpc-pv4p-pm3w). This repo never runs the LiteLLM proxy; it uses litellm
# only as an SDK client (litellm.acompletion/completion in web/app/api/v1/chat.py and
# infra/infra/libllm.py), so the vulnerable code path is not reachable. The fix is >=1.84.0,
# which requires openai>=2.20; web and agent_retrieval_agent are pinned litellm<1.83.0 +
# openai<2 pending an OpenAI v2 (Responses API) migration. infra is bumped to >=1.84.0.
ignore {
    input.PkgName == "litellm"
    input.VulnerabilityID == "CVE-2026-49468"
}

# chromadb CVE-2026-45829 (CRITICAL, "ChromaToast") — pre-auth RCE in the ChromaDB Python
# server. chromadb is an unused transitive dependency (pulled by crewai, which pins
# chromadb~=1.1.0); this repo runs no Chroma server and imports/instantiates no Chroma
# client or collection in source. There is no fixed chromadb version (latest 1.5.9 is still
# affected), so suppression is the only option. Re-evaluate when a fixed chromadb ships.
ignore {
    input.PkgName == "chromadb"
    input.VulnerabilityID == "CVE-2026-45829"
}

# chromadb CVE-2026-45833 (CRITICAL) — authenticated RCE, same code path as CVE-2026-45829
# above; unused transitive dep, no Chroma server/client run here, no fix exists yet.
ignore {
    input.PkgName == "chromadb"
    input.VulnerabilityID == "CVE-2026-45833"
}

# chromadb CVE-2026-45830 (HIGH) — cross-tenant read/write via V1 endpoints, no fix yet.
# Same unused-transitive-dep / no-Chroma-server reachability as the chromadb CVEs above.
ignore {
    input.PkgName == "chromadb"
    input.VulnerabilityID == "CVE-2026-45830"
}

# chromadb CVE-2026-45831 (HIGH) — SimpleRBACAuthorizationProvider ignores tenant/database/
# collection scope, no fix yet. Same reachability as the chromadb CVEs above.
ignore {
    input.PkgName == "chromadb"
    input.VulnerabilityID == "CVE-2026-45831"
}

# jupyter-server CVE-2026-44727 (CRITICAL) — stored XSS in NbconvertFileHandler. Trivy scans
# the lockfile, not the shipped artifact: jupyter-server is pulled only by the optional
# `agentic_playground` extra (jupyter-kernel-gateway) in agent_retrieval_agent and is NOT
# installed in the deployed production image (uv sync never uses --all-extras / that extra).
# A fix exists (>=2.20.0); bumping the optional extra is tracked as a later cleanup.
ignore {
    input.PkgName == "jupyter-server"
    input.VulnerabilityID == "CVE-2026-44727"
}
