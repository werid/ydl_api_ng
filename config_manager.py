import configparser
import copy
import json
import logging
import logging.handlers as handlers


class SectionConfig:
    __defaults = {
        '_api_route_download': '/download',
        '_api_route_extract_info': '/extract_info',
        '_api_route_info': '/info',
        '_api_route_active_downloads': '/active_downloads',
        '_enable_users_management': False,
        '_log_level': 20,
        '_log_backups': 7,
        '_listen_port': 80,
        '_listen_ip': '0.0.0.0'
    }

    def append(self, key, item):
        self.__dict__[key] = item

    def get(self, key):
        try:
            return self.__dict__[key]
        except KeyError:
            if self.__defaults is not None:
                return self.__defaults.get(key)
            return None

    def delete(self, key):
        try:
            self.__delattr__(key)
        except AttributeError:
            pass

    def get_all(self):
        return self.__dict__


class GlobalConfig:
    def add_section(self, group):
        self.__dict__[group] = SectionConfig()
        self.__dict__[group].append('_name', group)

    def get(self, key):
        try:
            return self.__dict__[key.upper()]
        except KeyError:
            return None

    def add_item(self, group, key, item):
        self.__dict__[group].append(key, item)

    def search_section_by_value(self, key, value):
        for item in self.__dict__:
            return_value = self.__dict__[item].get(key)
            if isinstance(return_value, list):
                if value in return_value:
                    return self.__dict__[item]
            elif return_value == value:
                return self.__dict__[item]
        return None

    def get_all(self):
        return self.__dict__


class ConfigManager:
    def __init__(self, params_file=None):
        self.__config = configparser.ConfigParser(interpolation=None)
        self.__presets_config = configparser.ConfigParser(interpolation=None)
        self.__site_config = configparser.ConfigParser(interpolation=None)
        self.__user_config = configparser.ConfigParser(interpolation=None)
        self.__app_config = configparser.ConfigParser(interpolation=None)
        self.__auth_config = configparser.ConfigParser(interpolation=None)
        self.__presets_config_object = GlobalConfig()
        self.__site_config_object = GlobalConfig()
        self.__user_config_object = GlobalConfig()
        self.__app_config_object = GlobalConfig()
        self.__auth_config_object = GlobalConfig()
        self.__keys_metadata = {}

        self.__config.read(params_file if params_file is not None else 'params/params.ini')

        self.__init_logger(self.__config['app'].getint('_log_level'), self.__config['app'].getint('_log_backups'))

        self.__dispatch_configs()
        self.__load_metadata()
        self.__set_config_objects()

    @staticmethod
    def __init_logger(level=30, backup_count=7):
        logging.basicConfig(level=level, format='[%(asctime)s][%(name)s][%(levelname)s] %(message)s', datefmt='%d-%m-%y %H:%M:%S')

        time_handler = handlers.TimedRotatingFileHandler('logs/ydl_api_ng', when='midnight', interval=1, backupCount=backup_count)
        time_handler.setLevel(level)
        time_handler.setFormatter(logging.Formatter('[%(asctime)s][%(name)s][%(levelname)s] %(message)s', datefmt='%d-%m-%y %H:%M:%S'))
        logging.getLogger().addHandler(time_handler)

        logging.getLogger('config_manager').info('Logger initialized')

    # Send configs to the right objects
    def __dispatch_configs(self):
        for section in self.__config.sections():
            if section.startswith('preset:'):
                self.__presets_config[section] = self.__expand_config(section)
            elif section.startswith('user:'):
                self.__user_config[section] = self.__expand_config(section)
            elif section.startswith('site:'):
                self.__site_config[section] = self.__expand_config(section)
            elif section.startswith('auth:'):
                self.__auth_config[section] = self.__expand_config(section)
            elif section == 'app':
                self.__app_config[section] = self.__config[section]

    # Resolve config expansions
    def __expand_config(self, section_name):
        temp_config = configparser.ConfigParser(interpolation=None)
        temp_config['__current_params'] = copy.deepcopy(self.__config[section_name])

        current_params = temp_config['__current_params']

        self.__expand_section(current_params, temp_config)

        # Merge with default to fill remaining parameters
        if self.__config.has_section(f'{section_name.split(":")[0]}:DEFAULT'):
            self.__merge_configs(self.__config[f'{section_name.split(":")[0]}:DEFAULT'], current_params, temp_config)
            self.__expand_section(current_params, temp_config)

        logging.getLogger('config_manager').debug(f'Expandig section {section_name}')
        return current_params

    def __expand_section(self, section, config_set):
        merged = False
        expendable_fields = ['_preset', '_template', '_location', '_auth', '_site', '_user']

        for key, value in section.items():
            if key in expendable_fields:
                merged = True
                config_set.remove_option(section.name, key)
                self.__merge_configs(self.__config[f'{key.lstrip("_")}:{value}'], section, config_set)

        if merged:
            self.__expand_section(section, config_set)

    # Merge expanded config into current config
    @staticmethod
    def __merge_configs(src, dest, config_set):
        for key, value in src.items():
            if not config_set.has_option(dest.name, key):
                dest[key] = value

    # Done on premise directly with objects, override values
    @staticmethod
    def merge_configs_object(user_object, preset_object):
        if user_object is not None:
            logging.getLogger('config_manager').debug(f'Merging preset {preset_object.get("_name")} in user {user_object.get("_name")}')

            for option in user_object.get_all():
                if option != '_name':
                    preset_object.append(option, user_object.get(option))

        return preset_object

    # Get parameters type from meta section of the parameters file
    def __load_metadata(self):
        logging.getLogger('config_manager').debug(f'Loading parameters metadata')

        params_meta_parser = configparser.ConfigParser(interpolation=None)
        params_meta_parser.read('params/params_metadata.ini')

        for key, value in params_meta_parser['meta'].items():
            if value != "":
                splitted = value.split(',')
            else:
                splitted = []
            self.__keys_metadata[key] = splitted

    def __set_config_objects(self):
        self.__populate_config_object(self.__app_config, self.__app_config_object)
        self.__populate_config_object(self.__presets_config, self.__presets_config_object)
        self.__populate_config_object(self.__user_config, self.__user_config_object)
        self.__populate_config_object(self.__site_config, self.__site_config_object)
        self.__populate_config_object(self.__auth_config, self.__auth_config_object)

    # Set python objects with the right type of object
    def __populate_config_object(self, config_set, config_set_object):
        logging.getLogger('config_manager').debug(f'Populate config objects with rights ')

        for section in config_set.sections():
            splitted_key = section.split(':')[-1].upper()

            config_set_object.add_section(splitted_key)
            for key, value in config_set[section].items():
                parsed_item = self.__get_parsed_parameter_value(key, value)
                logging.getLogger('config_manager').debug(f'Parameter parsing : {key} => {type(parsed_item).__name__}')

                config_set_object.add_item(splitted_key, key, parsed_item)

    def __get_parsed_parameter_value(self, key, value):
        if key in self.__keys_metadata.get('_int'):
            return int(value)
        if key in self.__keys_metadata.get('_float'):
            return float(value)
        if key in self.__keys_metadata.get('_bool'):
            return value == "true"
        if key in self.__keys_metadata.get('_array'):
            if value != '':
                return value.split(',')
            return None
        if key in self.__keys_metadata.get('_object'):
            return json.loads(value)

        # It's a string by default
        return value

    def is_user_permitted_by_token(self, user_token):
        manage_user = self.get_app_params().get('_enable_users_management')
        user = self.get_user_param_by_token(user_token)

        if manage_user:
            if user is None:
                logging.getLogger('auth').warning(f'Unauthorized user {user_token}')
                return False
            else:
                logging.getLogger('auth').info(f'Authorized user {user.get("_name")}')
                return user
        else:
            return None

    def get_all_users_params(self):
        return self.__user_config_object

    def get_user_param_by_token(self, token):
        return self.__user_config_object.search_section_by_value('_token', token)

    def get_all_preset_params(self):
        return self.__presets_config_object

    def get_preset_params(self, preset_name):
        return copy.deepcopy(self.__presets_config_object.get(preset_name))

    def get_all_sites_params(self):
        return self.__site_config_object

    def get_site_params(self, site_name):
        return self.__site_config_object.search_section_by_value('_hosts', site_name)

    def get_all_auth_params(self):
        return self.__auth_config_object

    def get_auth_params(self, preset_name):
        return self.__auth_config_object.get(preset_name)

    def get_keys_meta(self):
        return self.__keys_metadata

    def get_app_params(self):
        return self.__app_config_object.get('APP')

    def get_app_params_object(self):
        return self.__app_config_object

    # Remove hiddens fields to return on api
    def sanitize_config_object(self, config_object):
        clone_object = copy.deepcopy(config_object)

        for item in clone_object.get_all():
            self.sanitize_config_object_section(clone_object.get(item), True)

        return clone_object

    # Remove hiddens fields to return on api
    def sanitize_config_object_section(self, config_section_object, mutate=False):
        clone_object = config_section_object if mutate else copy.deepcopy(config_section_object)

        for hidden_field in self.__keys_metadata.get('_hidden'):
            clone_object.delete(hidden_field)

        return clone_object
