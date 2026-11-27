"""AgriFusion research lane: benchmark pipeline (core), external datasets (external), one-off studies (experiments).

Dependency direction: experiments -> external -> core -> agrifusion. core never imports external or
experiments; agrifusion never imports this package.
"""
