from flask import render_template

from flask_monitoringdashboard import blueprint
from flask_monitoringdashboard.core.auth import secure
from flask_monitoringdashboard.core.colors import get_color
from flask_monitoringdashboard.core.forms import get_slider_form
from flask_monitoringdashboard.core.info_box import get_plot_info
from flask_monitoringdashboard.core.plot import get_layout, get_figure, boxplot
from flask_monitoringdashboard.core.rules import get_rules
from flask_monitoringdashboard.database import session_scope, TestEndpoint
from flask_monitoringdashboard.database.count import count_builds_endpoint
from flask_monitoringdashboard.database.count_group import get_value, count_times_tested, get_latest_test_version, \
    get_previous_test_version
from flask_monitoringdashboard.database.data_grouped import get_test_data_grouped
from flask_monitoringdashboard.database.endpoint import get_last_requested
from flask_monitoringdashboard.database.tested_endpoints import get_tested_endpoint_names
from flask_monitoringdashboard.database.tests import get_travis_builds, \
    get_endpoint_measurements_job, get_last_tested_times, get_endpoint_measurements

AXES_INFO = '''The X-axis presents the execution time in ms. The Y-axis presents the
Travis builds of the Flask application.'''

CONTENT_INFO = '''In this graph, it is easy to compare the execution time of the different builds
to one another. This information may be useful to validate which endpoints need to be improved.'''


@blueprint.route('/endpoint_build_performance', methods=['GET', 'POST'])
@secure
def endpoint_build_performance():
    """
    Shows the performance results for the endpoint hits of a number of Travis builds.
    :return:
    """
    with session_scope() as db_session:
        form = get_slider_form(count_builds_endpoint(db_session), title='Select the number of builds')
    graph = get_boxplot_endpoints(form=form)
    return render_template('fmd_testmonitor/graph.html', graph=graph, title='Per-Build Endpoint Performance',
                           information=get_plot_info(AXES_INFO, CONTENT_INFO), form=form)


@blueprint.route('/testmonitor/<end>', methods=['GET', 'POST'])
@secure
def endpoint_test_details(end):
    """
    Shows the performance results for one specific unit test.
    :param end: the name of the unit test for which the results should be shown
    :return:
    """
    with session_scope() as db_session:
        form = get_slider_form(count_builds_endpoint(db_session), title='Select the number of builds')
    graph = get_boxplot_endpoints(endpoint=end, form=form)
    return render_template('fmd_testmonitor/endpoint.html', graph=graph, title='Per-Version Performance for ' + end,
                           information=get_plot_info(AXES_INFO, CONTENT_INFO), endp=end, form=form)


@blueprint.route('/testmonitor')
@secure
def testmonitor():
    """
    Gives an overview of the unit test performance results and the endpoints that they hit.
    :return:
    """
    from numpy import median
    import datetime
    week_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)
    four_weeks_ago = datetime.datetime.utcnow() - datetime.timedelta(days=28)

    with session_scope() as db_session:
        median_latest = get_test_data_grouped(db_session, median,
                                              TestEndpoint.app_version == get_latest_test_version(db_session))
        median_previous = get_test_data_grouped(db_session, median,
                                                TestEndpoint.app_version == get_previous_test_version(db_session))
        median_week = get_test_data_grouped(db_session, median,
                                            TestEndpoint.time_added > week_ago)
        median_four_weeks = get_test_data_grouped(db_session, median,
                                                  TestEndpoint.time_added > four_weeks_ago)
        tested_times = get_last_tested_times(db_session)

        result = []
        for endpoint in get_tested_endpoint_names(db_session):
            result.append({
                'name': endpoint,
                'color': get_color(endpoint),
                'latest': get_value(median_latest, endpoint),
                'previous': get_value(median_previous, endpoint),
                'week': get_value(median_week, endpoint),
                'four-weeks': get_value(median_four_weeks, endpoint),
                'last-tested': get_value(tested_times, endpoint, default=None)
            })

        return render_template('fmd_testmonitor/testmonitor.html', result=result)


@blueprint.route('/endpoint_coverage')
@secure
def endpoint_coverage():
    """
    Gives an overview of the coverage of the endpoints within the tested app.
    :return:
    """
    import datetime
    week_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)
    four_weeks_ago = datetime.datetime.utcnow() - datetime.timedelta(days=28)

    with session_scope() as db_session:
        tests_latest = count_times_tested(db_session, TestEndpoint.app_version == get_latest_test_version(db_session))
        tests_previous = count_times_tested(db_session,
                                            TestEndpoint.app_version == get_previous_test_version(db_session))
        tests_week = count_times_tested(db_session, TestEndpoint.time_added > week_ago)
        tests_four_weeks = count_times_tested(db_session, TestEndpoint.time_added > four_weeks_ago)
        tested_times = get_last_tested_times(db_session)

        result = []
        tested_endpoints = get_tested_endpoint_names(db_session)
        for endpoint in tested_endpoints:
            result.append({
                'name': endpoint,
                'color': get_color(endpoint),
                'latest': get_value(tests_latest, endpoint),
                'previous': get_value(tests_previous, endpoint),
                'week': get_value(tests_week, endpoint),
                'four-weeks': get_value(tests_four_weeks, endpoint),
                'last-tested': get_value(tested_times, endpoint, default=None)
            })

        last_accessed = get_last_requested(db_session)
        endpoints = []
        for rule in get_rules():
            if rule.endpoint not in tested_endpoints:
                endpoints.append({
                    'color': get_color(rule.endpoint),
                    'rule': rule.rule,
                    'endpoint': rule.endpoint,
                    'methods': rule.methods,
                    'last_accessed': get_value(last_accessed, rule.endpoint, default=None)
                })

        return render_template('fmd_testmonitor/coverage.html', result=result, untested_endpoints=endpoints)


def get_boxplot_endpoints(endpoint=None, form=None):
    """
    Generates a box plot visualization for the unit test endpoint hits performance results.
    :param endpoint: if specified, generate box plot for a specific endpoint, otherwise, generate for all tests
    :param form: the form that can be used for showing a subset of the data
    :return:
    """
    trace = []
    with session_scope() as db_session:
        if form:
            ids = get_travis_builds(db_session, limit=form.get_slider_value())
        else:
            ids = get_travis_builds(db_session)

        if not ids:
            return None
        for id in ids:
            if endpoint:
                values = get_endpoint_measurements_job(db_session, name=endpoint, job_id=id)
                trace.append(boxplot(values=values, label='{} -'.format(id), name=endpoint))
            else:
                values = get_endpoint_measurements(db_session, suite=id)
                trace.append(boxplot(values=values, label='{} -'.format(id), marker={'color': 'rgb(105, 105, 105)'}))

        layout = get_layout(
            xaxis={'title': 'Execution time (ms)'},
            yaxis={'title': 'Travis Build', 'autorange': 'reversed'}
        )

        return get_figure(layout=layout, data=trace)
