from abc import ABC, abstractmethod

class CancellationToken(ABC):
    """Universal abstraction for cancellation across any backend."""
    
    @abstractmethod
    def cancel(self) -> None:
        """Trigger the cancellation."""
        pass
        
    @abstractmethod
    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        pass
