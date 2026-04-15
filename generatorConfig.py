import os
from configparser import ConfigParser


class GeneratorConfigException(Exception):
    pass


def get_default_sessions_directory():
    """Return the platform-appropriate default sessions directory."""
    appdata = os.environ.get('APPDATA')
    if appdata:
        return os.path.join(appdata, 'CSVGenerator', 'sessions') + os.sep
    # Fallback for non-Windows platforms
    return os.path.join(os.path.expanduser('~'), '.csvgenerator', 'sessions') + os.sep


class GeneratorConfig(ConfigParser):
    def __init__(self, config_file):
        super(GeneratorConfig, self).__init__()

        self.read(config_file)
        self.validate_config()

    def get_sessions_directory(self):
        """Return the configured sessions directory, or the platform default if unset."""
        if 'sessions_directory' in self['DEFAULT'] and self['DEFAULT']['sessions_directory']:
            path = self['DEFAULT']['sessions_directory']
            if not path.endswith(('/', '\\')):
                path = path + os.sep
            return path
        return get_default_sessions_directory()

    def validate_config(self):
        required_values = {
            'DEFAULT': {
                'photoURLBeginning': None,
                'local_jpg_location': None,
                'working_directory': None,
                'templateFileName': None
            },
            'ssh': {
                'ssh_host': None,
                'ssh_username': None,
                'ssh_remote_file_path': None
            },
            'inputData': {
                'inputFileName': None,
                'inputHeader_description': None,
                'inputHeader_price': None,
                'inputHeader_count': None,
                'default_price': None
            }
        }
        # Can also use this format for options to restrict the accepted values:
        #   'mode': ('master', 'slave')

        for section, keys in required_values.items():
            if section not in self:
                raise GeneratorConfigException(
                    'Missing section %s in the config file' % section)

            for key, values in keys.items():
                if key not in self[section] or self[section][key] == '':
                    raise GeneratorConfigException((
                        'Missing value for %s under section %s in ' +
                        'the config file') % (key, section))

                if values:
                    if self[section][key] not in values:
                        raise GeneratorConfigException((
                            'Invalid value for %s under section %s in ' +
                            'the config file') % (key, section))
