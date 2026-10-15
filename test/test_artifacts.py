"""Offline tests: science products become artifact descriptors, never inline binary data."""

import asyncio
import base64
import hashlib
import io
import json
import os
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.table import Table
from astroquery.utils.commons import FileContainer
from fastmcp import Client

import executor
import server
from artifacts import ArtifactCall, get_store, guess_content_type
from executor import execute_function, serialize_result
from introspection import function_kind

DESCRIPTOR_FIELDS = {
    "artifact_id", "archive", "product_id", "filename", "content_type", "content_encoding",
    "size_bytes", "sha256", "download_url", "local_path", "resource_uri",
}


def make_hdulist() -> fits.HDUList:
    primary = fits.PrimaryHDU(np.arange(2000, dtype="f4").reshape(40, 50))
    primary.header["TELESCOP"] = "SDSS"
    primary.header["OBJECT"] = "M31"
    return fits.HDUList([primary, fits.ImageHDU(np.ones(10), name="SPEC")])


def fits_bytes() -> bytes:
    buffer = io.BytesIO()
    make_hdulist().writeto(buffer)
    return buffer.getvalue()


class TestDescriptor:
    def test_register_fits_file(self, tmp_path):
        path = tmp_path / "frame-r-001.fits"
        make_hdulist().writeto(path)
        descriptor = get_store().register(path, "sdss", "https://example.org/frame-r-001.fits")

        assert set(descriptor) == DESCRIPTOR_FIELDS | {"fits_summary"}
        assert descriptor["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert descriptor["artifact_id"] == descriptor["sha256"][:16]
        assert descriptor["size_bytes"] == path.stat().st_size
        assert descriptor["content_type"] == "application/fits"
        assert descriptor["product_id"] == "frame-r-001"
        assert descriptor["resource_uri"] == f"astroquery://artifacts/{descriptor['artifact_id']}"

        summary = descriptor["fits_summary"]
        assert summary["header"] == {"TELESCOP": "SDSS", "OBJECT": "M31"}
        assert [h["name"] for h in summary["hdus"]] == ["PRIMARY", "SPEC"]
        assert summary["hdus"][0]["shape"] == [40, 50]

    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("a.fits", ("application/fits", None)),
            ("a.fits.gz", ("application/fits", "gzip")),
            ("a.tar", ("application/x-tar", None)),
            ("a.vot", ("application/x-votable+xml", None)),
            ("a.unknownext", ("application/octet-stream", None)),
        ],
    )
    def test_content_types(self, filename, expected):
        assert guess_content_type(filename) == expected

    def test_store_lookup_rejects_bad_ids(self):
        assert get_store().get("../../etc/passwd") is None
        with pytest.raises(FileNotFoundError):
            get_store().read_bytes("0123456789abcdef")


class TestSerializeProducts:
    def test_hdulist_becomes_artifact(self):
        call = ArtifactCall(get_store(), "sdss")
        result = serialize_result([make_hdulist()], call)

        assert result == [{"artifact_id": call.descriptors[0]["artifact_id"], "filename": "sdss_product.fits"}]
        assert len(json.dumps(result)) < 200  # no pixel data in the model context
        assert Path(call.descriptors[0]["local_path"]).read_bytes()[:9] == b"SIMPLE  ="

    def test_binary_bytes_become_artifact(self):
        call = ArtifactCall(get_store(), "mast")
        ref = serialize_result(fits_bytes(), call)
        assert ref["filename"] == "mast_product.fits"
        assert call.descriptors[0]["content_type"] == "application/fits"

    def test_short_text_bytes_stay_inline(self):
        assert serialize_result(b"plain text") == "plain text"

    def test_large_array_becomes_npy_artifact_small_stays_inline(self):
        call = ArtifactCall(get_store(), "gaia")
        ref = serialize_result(np.zeros((100, 100)), call)
        assert ref["shape"] == [100, 100]
        assert call.descriptors[0]["content_type"] == "application/x-npy"
        assert serialize_result(np.arange(3)) == [0, 1, 2]

    def test_file_container_keeps_source_url(self, tmp_path):
        source = tmp_path / "spec-0266.fits"
        source.write_bytes(fits_bytes())
        container = FileContainer(str(source), encoding="binary", show_progress=False)

        call = ArtifactCall(get_store(), "sdss")
        ref = serialize_result([container], call)[0]
        descriptor = call.descriptors[0]
        assert ref["filename"] == "spec-0266.fits"
        assert descriptor["download_url"] == str(source)
        assert descriptor["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()

    def test_paths_only_become_artifacts_for_retrieval(self, tmp_path):
        path = tmp_path / "secret.txt"
        path.write_text("not a product")
        assert serialize_result(str(path), ArtifactCall(get_store(), "simbad")) == str(path)
        ref = serialize_result(str(path), ArtifactCall(get_store(), "esa_hubble", accept_paths=True))
        assert ref["filename"] == "secret.txt"

    def test_no_products_creates_no_directory(self, artifact_store):
        serialize_result(Table({"a": [1, 2]}), ArtifactCall(get_store(), "simbad"))
        assert not (artifact_store / "downloads").exists()


class FakeArchive:
    """Stands in for an astroquery class; mimics how real retrieval methods write files."""

    @staticmethod
    def download_data(observation_id):
        # Like XMM-Newton: no output-folder parameter, writes to the current directory
        Path(f"{observation_id}.tar").write_bytes(b"\x00tar" * 2000)
        return None

    @staticmethod
    def download_products(products, *, download_dir=None):
        # Like MAST: honours download_dir and returns a manifest table
        path = Path(download_dir) / "mastDownload" / f"{products}_drz.fits"
        path.parent.mkdir(parents=True)
        path.write_bytes(fits_bytes())
        return Table({"Local Path": [str(path)], "Status": ["COMPLETE"], "URL": [f"https://mast.example/{path.name}"]})

    @staticmethod
    def get_images(**kwargs):
        raise AssertionError("executor should call get_images_async to keep the URL")

    source_file: str = ""

    @classmethod
    def get_images_async(cls, **kwargs):
        return [FileContainer(cls.source_file, encoding="binary", show_progress=False)]

    @staticmethod
    def query_object(object_name):
        return Table({"name": [object_name]})


@pytest.fixture
def fake_archive(monkeypatch, tmp_path):
    source = tmp_path / "frame-r-000094-1-0012.fits"
    source.write_bytes(fits_bytes())
    monkeypatch.setattr(FakeArchive, "source_file", str(source))
    monkeypatch.setattr(executor, "get_class_instance", lambda module_name: FakeArchive)
    return FakeArchive


class TestExecuteRetrieval:
    def test_kind_classification(self):
        for name in ("download_products", "download_data", "get_images", "get_spectra_async", "get_product"):
            assert function_kind(name) == "retrieval", name
        for name in ("query_object", "get_product_list", "get_image_list", "get_cloud_uris"):
            assert function_kind(name) == "metadata", name

    def test_files_written_to_cwd_land_in_store(self, fake_archive, artifact_store):
        cwd = os.getcwd()
        response = execute_function("xmm_newton", "download_data", {"observation_id": "0505720401"})

        assert os.getcwd() == cwd
        assert response["kind"] == "retrieval"
        (descriptor,) = response["artifacts"]
        assert descriptor["filename"] == "0505720401.tar"
        assert Path(descriptor["local_path"]).is_relative_to(artifact_store)
        assert not Path(cwd, "0505720401.tar").exists()

    def test_download_dir_injected_and_urls_attached(self, fake_archive, artifact_store):
        response = execute_function("mast", "download_products", {"products": "hst_123"})
        (descriptor,) = response["artifacts"]
        assert descriptor["download_url"] == "https://mast.example/hst_123_drz.fits"
        assert descriptor["fits_summary"]["header"]["TELESCOP"] == "SDSS"
        assert Path(descriptor["local_path"]).is_relative_to(artifact_store)
        # The manifest table stays as small metadata
        assert response["result"]["data"][0]["Status"] == "COMPLETE"

    def test_get_images_uses_async_twin_for_url(self, fake_archive):
        response = execute_function("sdss", "get_images", {"band": "r"})
        (descriptor,) = response["artifacts"]
        assert descriptor["download_url"] == fake_archive.source_file
        assert response["result"] == [{"artifact_id": descriptor["artifact_id"], "filename": descriptor["filename"]}]
        assert "SIMPLE" not in json.dumps(response)

    def test_metadata_call_has_no_artifacts(self, fake_archive, artifact_store):
        response = execute_function("simbad", "query_object", {"object_name": "M31"})
        assert response["kind"] == "metadata"
        assert "artifacts" not in response
        assert not (artifact_store / "downloads").exists()


def test_artifact_resource_serves_bytes(fake_archive):
    response = execute_function("sdss", "get_images", {"band": "r"})
    descriptor = response["artifacts"][0]

    async def read(uri):
        async with Client(server.mcp) as client:
            return await client.read_resource(uri)

    (content,) = asyncio.run(read(descriptor["resource_uri"]))
    data = base64.b64decode(content.blob)
    assert hashlib.sha256(data).hexdigest() == descriptor["sha256"]

    with pytest.raises(Exception):
        asyncio.run(read("astroquery://artifacts/0123456789abcdef"))
