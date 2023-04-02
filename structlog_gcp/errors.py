import os

import structlog

from .types import CLOUD_LOGGING_KEY, ERROR_EVENT_TYPE, SOURCE_LOCATION_KEY


def add_service_context(logger, method_name, event_dict):
    """Add a service context in which an error has occurred.

    This is part of the Error Reporting API, so it's only added when an error happens.
    """

    event_type = event_dict[CLOUD_LOGGING_KEY].get("@type")
    if event_type != ERROR_EVENT_TYPE:
        return event_dict

    service_context = {
        # https://cloud.google.com/functions/docs/configuring/env-var#runtime_environment_variables_set_automatically
        "service": os.environ.get("K_SERVICE", "unknown service"),
        "version": os.environ.get("K_REVISION", "unknown version"),
    }

    # https://cloud.google.com/error-reporting/reference/rest/v1beta1/ServiceContext
    event_dict[CLOUD_LOGGING_KEY]["serviceContext"] = service_context

    return event_dict


class ReportException:
    """Transform exception into a Google Cloud Error Reporting event."""

    # https://cloud.google.com/error-reporting/reference/rest/v1beta1/projects.events/report
    # https://cloud.google.com/error-reporting/docs/formatting-error-messages#log-entry-examples

    def __init__(self, log_level="CRITICAL"):
        self.log_level = log_level

    def setup(self):
        return [
            # structlog.processors.ExceptionRenderer(self.format_exception),
            structlog.processors.format_exc_info,
            self.__call__,
        ]

    def __call__(self, logger, method_name, event_dict):
        exception = event_dict.pop("exception", None)
        if exception is None:
            return event_dict

        event_dict[CLOUD_LOGGING_KEY]["@type"] = ERROR_EVENT_TYPE
        event_dict[CLOUD_LOGGING_KEY]["severity"] = self.log_level

        # https://cloud.google.com/error-reporting/docs/formatting-error-messages
        message = event_dict[CLOUD_LOGGING_KEY]["message"]
        error_message = f"{message}\n{exception}"
        event_dict[CLOUD_LOGGING_KEY]["stack_trace"] = error_message

        return event_dict


class ReportError:
    """Report to Google Cloud Error Reporting specific log severities"""

    # https://cloud.google.com/error-reporting/reference/rest/v1beta1/projects.events/report
    # https://cloud.google.com/error-reporting/docs/formatting-error-messages#log-entry-examples

    def __init__(self, severities=None):
        if severities is None:
            severities = []

        self.severities = severities

    def setup(self):
        return [self.__call__]

    def _build_service_context(self):
        import os

        # https://cloud.google.com/error-reporting/reference/rest/v1beta1/ServiceContext
        service_context = {
            # https://cloud.google.com/functions/docs/configuring/env-var#runtime_environment_variables_set_automatically
            "service": os.environ.get("K_SERVICE", "unknown service"),
            "version": os.environ.get("K_REVISION", "unknown version"),
        }

        return service_context

    def __call__(self, logger, method_name, event_dict):
        severity = event_dict[CLOUD_LOGGING_KEY]["severity"]

        if severity not in self.severities:
            return event_dict

        event_dict[CLOUD_LOGGING_KEY]["@type"] = ERROR_EVENT_TYPE

        if SOURCE_LOCATION_KEY in event_dict[CLOUD_LOGGING_KEY]:
            # https://cloud.google.com/error-reporting/reference/rest/v1beta1/ErrorContext
            error_context = {
                "reportLocation": event_dict[CLOUD_LOGGING_KEY][SOURCE_LOCATION_KEY],
            }
            event_dict[CLOUD_LOGGING_KEY]["context"] = error_context
        else:
            event_dict[CLOUD_LOGGING_KEY]["context"] = "no location :("

        event_dict[CLOUD_LOGGING_KEY]["serviceContext"] = self._build_service_context()

        return event_dict