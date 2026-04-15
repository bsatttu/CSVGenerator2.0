from configparser import ConfigParser


class GeneratorConfigException(Exception):
    pass


class GeneratorConfig(ConfigParser):
    def __init__(self, config_file):
        super(GeneratorConfig, self).__init__()

        self.read(config_file)
        self.validate_config()

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
