# Author: Progradius
# License: AGPL 3.0

try:
    import usocket as socket
except:
    import socket

import gc

# Html header, containing css and scripts
html_header = """ 
<!DOCTYPE HTML>
    <html>
    <head>
    <meta charset="utf8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="//netdna.bootstrapcdn.com/bootstrap/3.1.0/css/bootstrap.min.css" rel="stylesheet" id="bootstrap-css">
      <link rel="stylesheet" href="https://use.fontawesome.com/releases/v5.7.2/css/all.css" integrity="sha384-fnmOCqbTlWIlj8LyTjo7mOUStjsKC4pOpQbqyi7RrhN7udi9RwhKkMHpvLbHG9Sr" crossorigin="anonymous">
      <style>
@import url('https://fonts.googleapis.com/css?family=Dosis:200,400');

body{
  background:black;
}

hr {
  border: 0;
  border-top: 3px solid white;
  border-bottom: 1px solid white;
  padding: 2px 0;
}

.mainwrap{
  width:20em;
  height:10em;
  background: rgba(0,0,0,.7);
  margin-top: 5px;
  margin-bottom:25px;
  padding:10px;
}
.formwrap{
  width:320px;
  height:480px;
  background: rgba(0,0,0,.7);
  margin:auto;
  margin-top:50px;
  padding:10px;
}

h1{
 font-family: 'Dosis', sans;
  font-size: 22px;
  font-weight:200;
  color:white;
  text-transform:uppercase;
  margin:0;
}
h2{
 font-family: 'Dosis', sans;
  font-size: 16px;
  font-weight:200;
  color:white;
  text-transform:uppercase;
}

p, a{
 font-family: 'Dosis', sans;
  font-size: 13px;
  font-weight:200;
  color:white;
  text-transform:none;
}

input:focus {
  /*border-color: rgba(82, 168, 236, 0.8);*/
  border-color: rgba(252, 247, 238, 0.8);
  outline: 0;
  outline: thin dotted \9;
  color:white;
}

input[type=hour], [type=number],[type=text]{
  font-family: 'Dosis', sans;
  font-size: 13px;
  font-weight:200;
  line-height: 2.1em; 
  color:#FCF7EE !important;
  background: transparent;
  border: 1px solid white;
  border-radius: 0px; 
  width: calc(100% - 12px);
  text-transform:none;
  padding-left:12px;
}
.button_base {
    margin: 0;
    border: 0;
    font-size: 18px;
  top:20px;
    position: relative;
  margin:auto;

    width: 100px;
    height: 42px;
    text-align: center;
    box-sizing: border-box;
    -webkit-box-sizing: border-box;
    -moz-box-sizing: border-box;
    -webkit-user-select: none;
    cursor: default;
}

.button_base:hover {
    cursor: pointer;
}

.simple_rollover {
    color: #000000;
    border: #000000 solid 1px;
    padding: 10px;
    background-color: #ffffff;
  font-family: 'Dosis', sans;
  font-size: 15px;
  font-weight:200;
  text-transform:uppercase;
}

.simple_rollover:hover {
    color: #ffffff;
    background-color: transparent;
    border:1px solid white;  
}
.div_center{
    text-align: center;
}      
</style>
      </head>
      <body>"""
# Html footer
html_footer = """</body></html>"""


def main_page(controller_status):
    gc.collect()
    """Main page: display system settings and sensor values"""
    # Dailytimer1 settings
    start_time = controller_status.get_dailytimer_current_start_time()
    stop_time = controller_status.get_dailytimer_current_stop_time()
    # Cyclic1 settings
    cyclic_duration = controller_status.get_cyclic_duration()
    cyclic_period = controller_status.get_cyclic_period()
    # Components state
    component_state = controller_status.get_component_state()

    # Html returned to the client
    html = """{header}<div class="container-fluid"> <div class="row"> <div class="col-md-12"> <h1 class="text-center"> Main Page. </h1> <br><br><div class="row"> <p><a href="/">System State</a></p><p><a href="monitor">Monitored Values</a></p><p><a href="conf">System Configuration</a></p><br><br><div class="col-md-6"> <h1>System Settings:</h1> <hr> <div class="row"> <div class="col-md-12 "> <div class="mainwrap"> <h1>DailyTimer #1: </h1> <hr> <h2>Start time:{start_time}</h2> <h2>Stop time:{stop_time}</h2> </div></div></div><div class="row"><div class="col-md-12"> <div class="mainwrap"> <h1>Cyclic #1:</h1> <hr> <h2>Action duration:{action}seconds</h2> <h2>Period:{period}minutes</h2> </div></div></div><div class="row"><div class="col-md-6"> <div class="mainwrap"> <h1>Component #1: </h1> <hr> <h2>State:{component}</h2> </div><div class="mainwrap"> <h1>Component #2: </h1> <hr> <h2>State:{component}</h2> </div></div></div></div></div></div>{footer}
    """.format(header=html_header,
               start_time=start_time, stop_time=stop_time,
               action=cyclic_duration, period=cyclic_period,
               component=component_state,
               footer=html_footer)

    del start_time
    del stop_time
    del cyclic_duration
    del component_state
    del html_header
    del html_footer

    gc.collect()
    return html


def conf_page():
    """System configuration page"""
    gc.collect()

    # Html returned to the client
    html = """  
    {header}  
    <section id="conf">
    <div class="container-fluid">
        <div class="row">
    	    <div class="col-md-6 col-xs-6">
    	        <h1 class="text-center">
                        Configuration Page.
                    </h1>
                    <br>
                    <br>
                <div class="row">
                <p><a href="/">System State</a></p>
                <p><a href="monitor">Monitored Values</a></p>
                <p><a href="conf">System Configuration</a></p>
                <br>
                <br>  
                <div class="formwrap">                
                  <h1>DailyTimer #1</h1>
                    <hr>                  
                  <p>Turn a component On and Off depending on time</p>
                  <br>
                  <h2>Settings</h2>

                  <form action="" method="get" class="dailytimer">
                  <h2>Start Hour: </h2>
                  <input type="hour" name="dt1start" value="17:00">
                  <h2>Stop Hour: </h2>
                  <input type="hour" name="dt1stop" value="11:00">                  
                 <div class="div_center"><input class="button_base simple_rollover" type="submit" value="Validate"></div>
                 </form>
                </div>
            </div>

      	    <div class="col-md-6 col-xs-6">
                <div class="formwrap">                
                  <h1>Cyclic #1</h1>
                    <hr>                  
                  <p>Turn a component On for a set amount of time, with a repeated period</p>
                  <br>
                  <h2>Settings</h2>

                  <form action="" method="get" class="cyclic1">
                  <h2>Period (in minutes): </h2>
                  <input type="number" name="period" value="10">
                  <h2>Action duration (in seconds): </h2>
                  <input type="number" name="duration" value="30">                  
                 <div class="div_center"><input class="button_base simple_rollover" type="submit" value="Validate"></div>
                 </form>
                </div>
            </div>
        </div>
    </div>
    <div class="container-fluid">
        <div class="row">

            <div class="col-md-6 col-xs-6">
                <div class="formwrap">                
                  <h1>Growth Stage:</h1>
                    <hr>                  
                  <p>Choose current growth stage</p>
                  <br>
                  <form action="" method="get" class="stage">
                  <h2>Stage: </h2>
                  <input type="text" name="stage" value="veg">             
                 <div class="div_center"><input class="button_base simple_rollover" type="submit" value="Validate"></div>
                 </form>
                </div>
            </div>
            <div class="col-md-6 col-xs-6">
                <div class="formwrap">                
                  <h1>Motor Speed:</h1>
                    <hr>                  
                  <p>Choose Motor Speed</p>
                  <br>
                  <form action="" method="get" class="speed">
                  <h2>Speed: </h2>
                  <input type="number" name="speed" value="1" min="1" max="4">             
                 <div class="div_center"><input class="button_base simple_rollover" type="submit" value="Validate"></div>
                 </form>
                </div>
            </div>
      	    </div>
    </div>
</section>
{footer}

""".format(header=html_header, footer=html_footer)
    gc.collect()
    return html


def monitor_page():
    gc.collect()
    # Html returned to the client
    html = """
    {header}
        <div class="container-fluid">
            <div class="row">
                <div class="col-md-12">
                    <h1 class="text-center">
                        Monitor Page.
                    </h1>
                    <br>
                    <br>
                <div class="row">
                <p><a href="/">System State</a></p>
                <p><a href="monitor">Monitored Values</a></p>
                <p><a href="conf">System Configuration</a></p>
                <br>
                <br>      
                
                    <div class="col-md-6">
                        <h1>Monitored Values:</h1>
                        <hr>
                            <div class="row">
                                <div class="col-md-6"> 
                                    <h1>BME280</h1>
                                    <hr>
            
                                    <div class="mainwrap">
                                        <h1>Temperature: </h1>
                                        <hr>
                                        <h2>28°c</h2>
                                    </div>
                                     <div class="mainwrap">
                                        <h1>Hygrometry: </h1>
                                        <hr>
                                        <h2>66%</h2>
                                    </div>
                                    <div class="mainwrap">
                                        <h1>Pressure: </h1>
                                        <hr>
                                        <h2>777hPa</h2>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                            <div class="row">
                                <div class="col-md-6">
                                    <h1>DS18B</h1>
                                    <hr>
                                    <div class="mainwrap">
                                        <h1>Temperature DSB18 #1: </h1>
                                        <hr>
                                        <h2>28°c</h2>
                                    </div>
                                     <div class="mainwrap">
                                        <h1>Hygrometry DSB18 #2: </h1>
                                        <hr>
                                        <h2>66%</h2>
                                    </div>
                                    <div class="mainwrap">
                                        <h1>Hygrometry DSB18 #3: </h1>
                                        <hr>
                                        <h2>66%</h2>
                                    </div>
                                </div>
                            </div>					    
                        </div>
                    </div>
                </div>
        </div>
        {footer}
    """.format(header=html_header, footer=html_footer)
    gc.collect()
    return html
