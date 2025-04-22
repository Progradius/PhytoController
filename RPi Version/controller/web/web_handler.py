# Author: Progradius
# License: AGPL 3.0

# Pas besoin d'import socket ici car ce fichier ne fait pas de réseau directement
# Pas de gestion mémoire nécessaire (pas de `gc`)

# ========== HEADER & FOOTER HTML ==========

html_header = """ 
<!DOCTYPE HTML>
<html>
<head>
<meta charset="utf8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link href="//netdna.bootstrapcdn.com/bootstrap/3.1.0/css/bootstrap.min.css" rel="stylesheet" id="bootstrap-css">
<link rel="stylesheet" href="https://use.fontawesome.com/releases/v5.7.2/css/all.css"
      integrity="sha384-fnmOCqbTlWIlj8LyTjo7mOUStjsKC4pOpQbqyi7RrhN7udi9RwhKkMHpvLbHG9Sr"
      crossorigin="anonymous">
<style>
@import url('https://fonts.googleapis.com/css?family=Dosis:200,400');
/* CSS custom ici */
body{ background:black; }
/* ... tout le reste inchangé ... */
</style>
</head>
<body>"""

html_footer = """</body></html>"""

# ========== PAGES ==========

def main_page(controller_status):
    """Page principale : état système + timers"""
    start_time = controller_status.get_dailytimer_current_start_time()
    stop_time = controller_status.get_dailytimer_current_stop_time()
    cyclic_duration = controller_status.get_cyclic_duration()
    cyclic_period = controller_status.get_cyclic_period()
    component_state = controller_status.get_component_state()

    html = """{header}
    <div class="container-fluid">
        <div class="row">
            <div class="col-md-12">
                <h1 class="text-center"> Main Page. </h1>
                <br><br>
                <p><a href="/">System State</a></p>
                <p><a href="monitor">Monitored Values</a></p>
                <p><a href="conf">System Configuration</a></p>
                <br><br>

                <div class="col-md-6">
                    <h1>System Settings:</h1>
                    <hr>
                    <div class="mainwrap">
                        <h1>DailyTimer #1: </h1><hr>
                        <h2>Start time: {start_time}</h2>
                        <h2>Stop time: {stop_time}</h2>
                    </div>
                    <div class="mainwrap">
                        <h1>Cyclic #1:</h1><hr>
                        <h2>Action duration: {action}s</h2>
                        <h2>Period: {period}min</h2>
                    </div>
                    <div class="mainwrap">
                        <h1>Component #1: </h1><hr>
                        <h2>State: {component}</h2>
                    </div>
                    <div class="mainwrap">
                        <h1>Component #2: </h1><hr>
                        <h2>State: {component}</h2>
                    </div>
                </div>
            </div>
        </div>
    </div>
    {footer}
    """.format(header=html_header, start_time=start_time, stop_time=stop_time,
               action=cyclic_duration, period=cyclic_period, component=component_state, footer=html_footer)

    return html


def conf_page():
    """Page de configuration"""
    return html_header + """  
    <!-- Formulaire de configuration -->
    <section id="conf">
    <div class="container-fluid">
        <div class="row">
            <div class="col-md-6">
                <div class="formwrap">
                    <h1>DailyTimer #1</h1><hr>
                    <form action="" method="get" class="dailytimer">
                        <h2>Start Hour:</h2>
                        <input type="hour" name="dt1start" value="17:00">
                        <h2>Stop Hour:</h2>
                        <input type="hour" name="dt1stop" value="11:00">
                        <div class="div_center">
                            <input class="button_base simple_rollover" type="submit" value="Validate">
                        </div>
                    </form>
                </div>
            </div>
            <div class="col-md-6">
                <div class="formwrap">
                    <h1>Cyclic #1</h1><hr>
                    <form action="" method="get" class="cyclic1">
                        <h2>Period (min):</h2>
                        <input type="number" name="period" value="10">
                        <h2>Action duration (sec):</h2>
                        <input type="number" name="duration" value="30">
                        <div class="div_center">
                            <input class="button_base simple_rollover" type="submit" value="Validate">
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>
    </section>
    """ + html_footer


def monitor_page():
    """Page de monitoring (affichage fixe simulé ici)"""
    html = """
    {header}
    <div class="container-fluid">
        <div class="row">
            <div class="col-md-12">
                <h1 class="text-center">Monitor Page</h1>
                <p><a href="/">System State</a></p>
                <p><a href="monitor">Monitored Values</a></p>
                <p><a href="conf">System Configuration</a></p>
                <br><br>
                <div class="col-md-6">
                    <h1>BME280</h1><hr>
                    <div class="mainwrap"><h1>Temperature:</h1><hr><h2>28°C</h2></div>
                    <div class="mainwrap"><h1>Hygrometry:</h1><hr><h2>66%</h2></div>
                    <div class="mainwrap"><h1>Pressure:</h1><hr><h2>777hPa</h2></div>
                </div>
                <div class="col-md-6">
                    <h1>DS18B</h1><hr>
                    <div class="mainwrap"><h1>Temp DSB18 #1:</h1><hr><h2>28°C</h2></div>
                    <div class="mainwrap"><h1>Hygro DSB18 #2:</h1><hr><h2>66%</h2></div>
                    <div class="mainwrap"><h1>Hygro DSB18 #3:</h1><hr><h2>66%</h2></div>
                </div>
            </div>
        </div>
    </div>
    {footer}
    """.format(header=html_header, footer=html_footer)

    return html
