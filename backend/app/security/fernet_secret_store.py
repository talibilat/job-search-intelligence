from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from app.config import AppSettings
from app.security.secret_store import SecretRef, SecretStoreUnavailableError

_PRIVATE_FILE_MODE = 0o600


class FernetSecretStore:
    """File-backed SecretStore adapter that encrypts each secret with Fernet."""

    def __init__(self, *, key_file: Path, store_dir: Path) -> None:
        self._key_file = key_file.expanduser()
        self._store_dir = store_dir.expanduser()
        self._fernet: Fernet | None = None

    @classmethod
    def from_settings(cls, settings: AppSettings) -> FernetSecretStore:
        return cls(
            key_file=settings.fernet_key_file,
            store_dir=settings.data_dir / "secrets",
        )

    async def get_secret(self, ref: SecretRef) -> SecretStr | None:
        secret_file = self._secret_file(ref)
        if not secret_file.exists():
            return None

        try:
            encrypted_value = secret_file.read_bytes()
            decrypted_value = self._load_fernet_for_read().decrypt(encrypted_value)
            return SecretStr(decrypted_value.decode("utf-8"))
        except (OSError, InvalidToken, UnicodeDecodeError) as error:
            raise SecretStoreUnavailableError(
                "Encrypted secret payload could not be read."
            ) from error

    async def set_secret(self, ref: SecretRef, value: SecretStr) -> None:
        secret_file = self._secret_file(ref)
        try:
            secret_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise SecretStoreUnavailableError(
                "Encrypted secret payload could not be written."
            ) from error

        encrypted_value = self._load_or_create_fernet().encrypt(
            value.get_secret_value().encode("utf-8")
        )
        self._write_private_file(secret_file, encrypted_value)

    async def delete_secret(self, ref: SecretRef) -> None:
        secret_file = self._secret_file(ref)
        try:
            secret_file.unlink()
        except FileNotFoundError:
            return
        except OSError as error:
            raise SecretStoreUnavailableError(
                "Encrypted secret payload could not be deleted."
            ) from error

    def _secret_file(self, ref: SecretRef) -> Path:
        return self._store_dir / ref.kind.value / ref.provider / f"{ref.name}.fernet"

    def _load_fernet_for_read(self) -> Fernet:
        return self._load_fernet(create_if_missing=False)

    def _load_or_create_fernet(self) -> Fernet:
        return self._load_fernet(create_if_missing=True)

    def _load_fernet(self, *, create_if_missing: bool) -> Fernet:
        if self._fernet is not None:
            return self._fernet

        key = self._load_or_create_key(create_if_missing=create_if_missing)
        try:
            self._fernet = Fernet(key)
        except ValueError as error:
            raise SecretStoreUnavailableError("Fernet secret key is invalid.") from error

        return self._fernet

    def _load_or_create_key(self, *, create_if_missing: bool) -> bytes:
        if self._key_file.exists():
            return self._read_key_file()

        if not create_if_missing:
            raise SecretStoreUnavailableError("Fernet secret key file is missing.")

        key = Fernet.generate_key()
        try:
            self._key_file.parent.mkdir(parents=True, exist_ok=True)
            self._write_new_private_file(self._key_file, key)
        except FileExistsError:
            return self._read_key_file()
        except OSError as error:
            raise SecretStoreUnavailableError("Fernet secret key could not be created.") from error

        return key

    def _read_key_file(self) -> bytes:
        try:
            return self._key_file.read_bytes().strip()
        except OSError as error:
            raise SecretStoreUnavailableError("Fernet secret key could not be read.") from error

    @staticmethod
    def _write_private_file(path: Path, content: bytes) -> None:
        temp_path = path.with_name(f".{path.name}.tmp")
        try:
            FernetSecretStore._write_or_replace_private_file(temp_path, content)
            temp_path.replace(path)
            os.chmod(path, _PRIVATE_FILE_MODE)
        except OSError as error:
            with suppress(OSError):
                temp_path.unlink()
            raise SecretStoreUnavailableError(
                "Encrypted secret payload could not be written."
            ) from error

    @staticmethod
    def _write_or_replace_private_file(path: Path, content: bytes) -> None:
        file_descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            _PRIVATE_FILE_MODE,
        )
        with os.fdopen(file_descriptor, "wb") as file:
            file.write(content)

    @staticmethod
    def _write_new_private_file(path: Path, content: bytes) -> None:
        file_descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            _PRIVATE_FILE_MODE,
        )
        with os.fdopen(file_descriptor, "wb") as file:
            file.write(content)
