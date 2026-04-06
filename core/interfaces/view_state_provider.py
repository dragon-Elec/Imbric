from abc import ABC, abstractmethod
from typing import Optional
from core.models.view_state import ViewState


class ViewStateProvider(ABC):
    """
    Contract for reading and writing directory-specific presentation settings.
    Implementations (like GIO) persist this data transparently (e.g. via GVfs Metadata).
    """

    @abstractmethod
    def get_view_state(self, path_or_uri: str) -> Optional[ViewState]:
        """
        Read the saved view state for a given path.
        Returns None if no saved state exists or if the path is unmonitorable/virtual.
        """
        pass

    @abstractmethod
    def set_view_state(self, path_or_uri: str, state: ViewState) -> None:
        """
        Persist a partial or full view state for a given path.
        Only the non-None fields in the ViewState object should be updated.
        """
        pass
