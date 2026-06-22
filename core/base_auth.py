from abc import ABC, abstractmethod

class BaseAuth(ABC):
    """
    Interface base abstrata para todos os provedores de autenticação (Microsoft, Google, etc.).
    Garante que qualquer provedor tenha a mesma assinatura de métodos.
    """

    @classmethod
    @abstractmethod
    def get_instance(cls):
        pass

    @abstractmethod
    def get_token_silent(self) -> str | None:
        pass

    @abstractmethod
    def login_interactive(self) -> bool:
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        pass
