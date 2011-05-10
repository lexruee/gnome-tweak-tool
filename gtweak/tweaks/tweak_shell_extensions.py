import os.path
import shutil
import zipfile
import tempfile
import logging
import json

from gi.repository import Gtk
from gi.repository import GLib

from gtweak.utils import extract_zip_file
from gtweak.gsettings import GSettingsSetting
from gtweak.gshellwrapper import GnomeShell
from gtweak.tweakmodel import Tweak, TweakGroup
from gtweak.widgets import ZipFileChooserButton, build_label_beside_widget, build_horizontal_sizegroup

class _ShellExtensionTweak(Tweak):

    EXTENSION_DISABLED_KEY = "disabled-extensions"

    def __init__(self, shell, ext, settings, **options):
        Tweak.__init__(self, ext["name"], ext.get("description",""), **options)

        self._shell = shell
        self._settings = settings

        sw = Gtk.Switch()
        state = ext.get("state")
        sw.set_active(
                state == 1 and \
                not self._settings.setting_is_in_list(self.EXTENSION_DISABLED_KEY, ext["uuid"])
        )
        sw.set_sensitive(state in (1,2))
        sw.connect('notify::active', self._on_extension_toggled, ext["uuid"])

        self.widget = build_label_beside_widget(
                        "%s Extension" % ext["name"],
                        sw)
        self.widget_for_size_group = sw

    def _on_extension_toggled(self, sw, active, uuid):
        if not sw.get_active():
            self._settings.setting_add_to_list(self.EXTENSION_DISABLED_KEY, uuid)
        else:
            self._settings.setting_remove_from_list(self.EXTENSION_DISABLED_KEY, uuid)

        self.notify_action_required(
            "The shell must be restarted for changes to take effect",
            "Restart",
            lambda: self._shell.restart())

class _ShellExtensionInstallerTweak(Tweak):

    EXTENSION_DIR = os.path.join(GLib.get_user_data_dir(), "gnome-shell", "extensions")

    def __init__(self, shell, **options):
        Tweak.__init__(self, "Install shell extension", "", **options)

        self._shell = shell

        chooser = ZipFileChooserButton("Select a theme file")
        chooser.connect("file-set", self._on_file_set)

        self.widget = build_label_beside_widget(self.name, chooser)
        self.widget_for_size_group = chooser

    def _on_file_set(self, chooser):
        f = chooser.get_filename()

        with zipfile.ZipFile(f, 'r') as z:
            try:
                fragment = ()
                file_extension = None
                file_metadata = None
                for n in z.namelist():
                    if n.endswith("metadata.json"):
                        fragment = n.split("/")[0:-1]
                        file_metadata = n
                    if n.endswith("extension.js"):
                        extension = True
                        file_extension = n

                if not file_metadata:
                    raise Exception("Could not find metadata.json")
                if not file_extension:
                    raise Exception("Could not find extension.js")

                #extract the extension uuid
                extension_uuid = None
                tmp = tempfile.mkdtemp()
                z.extract(file_metadata, tmp)
                with open(os.path.join(tmp,file_metadata)) as f:
                    try:
                        extension_uuid = json.load(f)["uuid"]
                    except:
                        logging.warning("Invalid extension format", exc_info=True)

                ok = False
                if extension_uuid:
                    ok, updated = extract_zip_file(
                                    z,
                                    "/".join(fragment),
                                    os.path.join(self.EXTENSION_DIR, extension_uuid))

                if ok:
                    if updated:
                        verb = "%s extension updated successfully" % extension_uuid
                    else:
                        verb = "%s extension installed successfully" % extension_uuid

                    self.notify_action_required(
                        verb,
                        "Restart",
                        lambda: self._shell.restart())

                else:
                    self.notify_error("Error installing extension")


            except:
                #does not look like a valid theme
                self.notify_error("Invalid extension file")
                logging.warning("Error parsing theme zip", exc_info=True)

        #set button back to default state
        chooser.unselect_all()

class ShellExtensionTweakGroup(TweakGroup):
    def __init__(self):
        extension_tweaks = []
        sg = build_horizontal_sizegroup()

        #check the shell is running
        try:
            shell = GnomeShell()

            #add the extension installer
            extension_tweaks.append(
                _ShellExtensionInstallerTweak(shell, size_group=sg))

            try:
                settings = GSettingsSetting("org.gnome.shell")
                #add a tweak for each installed extension
                for extension in shell.list_extensions().values():
                    try:
                        extension_tweaks.append(
                            _ShellExtensionTweak(shell, extension, settings, size_group=sg))
                    except:
                        logging.warning("Invalid extension", exc_info=True)
            except:
                logging.warning("Error listing extensions", exc_info=True)
        except:
            logging.warning("Error detecting shell")

        TweakGroup.__init__(self, "Shell Extensions", *extension_tweaks)

TWEAK_GROUPS = (
        ShellExtensionTweakGroup(),
)
