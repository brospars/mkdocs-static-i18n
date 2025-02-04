import os
from pathlib import Path
from re import compile
from urllib.parse import quote as urlquote

from mkdocs import utils
from mkdocs.config.base import ValidationError
from mkdocs.config.config_options import Type
from mkdocs.structure.files import File, Files

RE_LOCALE = compile(r"(^[a-z]{2}_[A-Z]{2}$)|(^[a-z]{2}$)")


class Locale(Type):
    """
    Locale Config Option

    Validate the locale config option against a given Python type.
    """

    def _validate_locale(self, value):
        if not RE_LOCALE.match(value):
            raise ValidationError(
                "Language code values must be either ISO-639-1 lower case "
                "or represented with they territory/region/county codes, "
                f"received '{value}' expected forms examples: 'en' or 'en_US'."
            )

    def run_validation(self, value):
        value = super().run_validation(value)
        if isinstance(value, str):
            self._validate_locale(value)
        if isinstance(value, dict):
            for key in value:
                self._validate_locale(key)
        return value


class I18nFiles(Files):
    """
    This class extends MkDocs' Files class to support links and assets that
    have a translated locale suffix.

    Since MkDocs relies on the file.src_path of pages and assets we have to
    derive the file.src_path and check for a possible .<locale>.<suffix> file
    to use instead of the link / asset referenced in the markdown source.
    """

    locale = None
    translated = False

    def append(self, file):
        """
        Since i18nFile find their own language versions, we need to avoid adding
        them multiple times when a localized version of a file is considered.

        The first i18nFile is sufficient to cover all their possible localized versions.
        """
        for inside_file in [*self._files]:
            if inside_file.dest_path == file.dest_path:
                return
        self._files.append(file)

    def __contains__(self, path):
        """
        Return a bool stipulating whether or not we found a translated version
        of the given path or the path itself.

        Since our plugin automatically localize links, this is useful for the
        mkdocs.structure.pages / path_to_url() method to point to the localized
        version of the file, if present.
        """
        expected_src_path = Path(path)
        expected_src_paths = [
            expected_src_path.with_suffix(f".{self.locale}{expected_src_path.suffix}"),
            expected_src_path.with_suffix(
                f".{self.default_locale}{expected_src_path.suffix}"
            ),
            expected_src_path,
        ]
        return any(filter(lambda s: Path(s) in expected_src_paths, self.src_paths))

    def get_file_from_path(self, path):
        """ Return a File instance with File.src_path equal to path. """
        expected_src_path = Path(path)
        expected_src_paths = [
            expected_src_path.with_suffix(f".{self.locale}{expected_src_path.suffix}"),
            expected_src_path.with_suffix(
                f".{self.default_locale}{expected_src_path.suffix}"
            ),
            expected_src_path,
        ]
        for src_path in filter(lambda s: Path(s) in expected_src_paths, self.src_paths):
            return self.src_paths.get(os.path.normpath(src_path))


class I18nFile(File):
    """
    This is a i18n aware version of a mkdocs.structure.files.File
    """

    def __init__(
        self,
        file_from,
        language,
        all_languages=None,
        default_language=None,
        docs_dir=None,
        site_dir=None,
        use_directory_urls=None,
    ) -> None:
        # preserved from mkdocs.structure.files.File
        # since they are not calculated
        self.page = file_from.page
        self.docs_dir = docs_dir
        self.site_dir = site_dir

        # i18n addons
        self.all_languages = all_languages
        self.dest_language = language
        self.initial_abs_src_path = file_from.abs_src_path
        self.initial_abs_dest_path = file_from.abs_dest_path
        self.initial_dest_path = file_from.dest_path
        self.initial_src_path = file_from.src_path
        self.locale_suffix = None

        # the name without any suffix
        self.name = self._get_stem()

        # find src_path
        expected_paths = [
            (
                language,
                Path(docs_dir)
                / Path(f"{self.non_i18n_src_path}.{language}{self.suffix}"),
            ),
            (
                default_language,
                Path(docs_dir)
                / Path(f"{self.non_i18n_src_path}.{default_language}{self.suffix}"),
            ),
            (None, Path(docs_dir) / Path(f"{self.non_i18n_src_path}{self.suffix}")),
        ]
        for locale_suffix, expected_path in expected_paths:
            if Path(expected_path).exists():
                self.src_path = expected_path.relative_to(self.docs_dir)
                self.abs_src_path = Path(self.docs_dir) / Path(self.src_path)
                #
                self.locale_suffix = locale_suffix
                if self.locale_suffix:
                    self.dest_name = Path(self.name).with_suffix(self.suffix)
                else:
                    self.dest_name = Path(self.name).with_suffix(
                        "".join(Path(self.initial_src_path).suffixes)
                    )
                #
                self.dest_path = self._get_dest_path(use_directory_urls)
                self.abs_dest_path = (
                    Path(self.site_dir)
                    / Path(self.dest_language)
                    / Path(self.dest_path)
                )
                break
        else:
            self.src_path = file_from.src_path
            self.abs_src_path = file_from.abs_src_path
            #
            self.dest_path = file_from.dest_path
            self.abs_dest_path = file_from.abs_dest_path

        # set url
        self.url = self._get_url(use_directory_urls)

        # mkdocs expects strings for those
        self.abs_dest_path = str(self.abs_dest_path)
        self.abs_src_path = str(self.abs_src_path)
        self.dest_path = str(self.dest_path)
        self.src_path = str(self.src_path)

    def __repr__(self):
        return (
            f"I18nFile(src_path='{self.src_path}', abs_src_path='{self.abs_src_path}',"
            f" dest_path='{self.dest_path}', abs_dest_path='{self.abs_dest_path}',"
            f" name='{self.name}', locale_suffix='{self.locale_suffix}',"
            f" dest_language='{self.dest_language}', dest_name='{self.dest_name}',"
            f" url='{self.url}')"
        )

    @property
    def non_i18n_src_path(self):
        """
        Return the path of the given page without any suffix.
        """
        if self._is_localized_for() is None:
            non_i18n_src_path = Path(self.initial_src_path).with_suffix("")
        else:
            non_i18n_src_path = (
                Path(self.initial_src_path).with_suffix("").with_suffix("")
            )
        return non_i18n_src_path

    def _is_localized_for(self):
        """
        Returns the locale detected in the file's suffixes <name>.<locale>.<suffix>.
        """
        for language in self.all_languages:
            expected_suffixes = [f".{language}", Path(self.initial_src_path).suffix]
            if set(expected_suffixes) <= set(Path(self.initial_src_path).suffixes):
                return language
        return None

    @property
    def suffix(self):
        return Path(self.initial_src_path).suffix

    def _get_stem(self):
        """ Return the name of the file without it's extension. """
        return (
            "index"
            if self.non_i18n_src_path.name in ("index", "README")
            else self.non_i18n_src_path.name
        )

    def _get_dest_path(self, use_directory_urls):
        """ Return destination path based on source path. """
        parent, _ = os.path.split(self.src_path)
        if self.is_documentation_page():
            if use_directory_urls is False or self.name == "index":
                # index.md or README.md => index.html
                # foo.md => foo.html
                return os.path.join(parent, self.name + ".html")
            else:
                # foo.md => foo/index.html
                return os.path.join(parent, self.name, "index.html")
        else:
            return os.path.join(parent, self.dest_name)

    def _get_url(self, use_directory_urls):
        """ Return url based in destination path. """
        url = str(self.dest_path).replace(os.path.sep, "/")
        dirname, filename = os.path.split(url)
        if use_directory_urls and filename == "index.html":
            if dirname == "":
                url = "."
            else:
                url = dirname + "/"
        if self.dest_language:
            if url == ".":
                url = self.dest_language + "/"
            else:
                url = self.dest_language + "/" + url
        return urlquote(url)

    def url_relative_to(self, other):
        """ Return url for file relative to other i18n file. """
        return utils.get_relative_url(
            self.url,
            other.url
            if (isinstance(other, File) or isinstance(other, I18nFile))
            else other,
        )
