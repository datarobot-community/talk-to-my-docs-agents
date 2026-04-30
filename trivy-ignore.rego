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
