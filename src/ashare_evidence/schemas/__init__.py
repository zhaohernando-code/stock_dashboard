"""Schema domain barrel — re-exports all Pydantic models."""
from .stock import *
from .simulation import *
from .portfolio import *
from .operations import *
from .runtime import *
from .research import *

# Resolve forward references across domain files
# Models in stock with cross-domain refs are handled via TYPE_CHECKING
# Models in simulation with cross-domain refs are handled via TYPE_CHECKING
# Models in portfolio with cross-domain refs are handled via TYPE_CHECKING
# Models in operations with cross-domain refs are handled via TYPE_CHECKING
# Models in runtime with cross-domain refs are handled via TYPE_CHECKING
# Models in research with cross-domain refs are handled via TYPE_CHECKING
