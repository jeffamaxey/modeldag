import numpy as np
import pandas
import inspect
import warnings
from copy import deepcopy

#__all__ = ["ModelDAG"]

def modeldict_to_modeldf(model):
    """ """
    dd = pandas.DataFrame(list(model.values()), 
                          index=model.keys()).reset_index(names=["model_name"])
    if "as" not in dd:
        dd["as"] = dd["model_name"]
        dd["entry"] = dd["as"]
    else:
        # naming convention
        f_ = dd["as"].fillna( dict(dd["model_name"]) )
        f_.name = "entry"
        dd = dd.join(f_) # merge and explode the names and inputs
        
    return dd

class ModelDAG( object ):
    """
    Models are dict of arguments that may have 3 entries:
    model = {key1 : {'func': func, 'kwargs': dict, 'as': None_str_list'},
             key2 : {'func': func, 'kwargs': dict, 'as': None_str_list'},
             ...
             }
    
    """
    def __init__(self, model={}, obj=None):
        """ 
        
        Parameters
        ----------
        model: dict
            dictionary descripting the model DAG

        obj: object
            instance the model is attached too. It may contain 
            method called by the DAG.

        Returns
        -------
        instance
        """
        self.model = model
        self.obj = obj

    def __str__(self):
        """ """
        import pprint
        return pprint.pformat(self.model, sort_dicts=False)

    def __repr__(self):
        """ """
        return self.__str__()


    def to_graph(self, engine="networkx"):
        """ converts the model into another graph library object 

        Parameters
        ----------
        engine: string
            Implemented:
            - NetworkX (networkx.org/documentation/stable/tutorial.html)
            - Graphviz (https://pygraphviz.github.io/documentation/stable/index.html)

        Return
        ------
        Graph instance
            a new instance object.
        """
        if engine == "networkx":
            import networkx as nx
            graph = nx.Graph()
        elif engine in ["graphviz", "pygraphviz"]:
            import pygraphviz as pgv
            graph = pgv.AGraph(directed=True, strict=True)
        else:
            raise NotImplementedError(f"engine {engine} is not implemented. networkx and graphviz are")

        # Nodes and Edges
        for name in self.entries:
            graph.add_node(name)
    
        for name, to_name in self.entry_inputof.items():
            graph.add_edge(name, to_name)

        return graph
    
    def to_networkx(self):
        """ shortcut to to_graph('networkx') """
        return self.to_graph(engine="networkx")

    def to_graphviz(self):
        """ shortcut to to_graph('graphviz') """
        return self.to_graph(engine="graphviz")


    # ============ #
    #   Method     #
    # ============ #
    def visualize(self, fileout="tmp_modelvisualize.svg"):
        """ """
        from IPython.display import SVG
        
        ag = self.to_graphviz()
        ag.graph_attr["epsilon"] = "0.001"
        
        ag.layout("dot")  # layout with dot
        ag.draw(fileout)
        return SVG(fileout)

    def get_model(self, funcs={}, **kwargs):
        """ get a copy of the model 
        
        Parameters
        ----------
        funcs: dict
            change the model's entry function:
            for instance change "a" to a uniform distribution
            funcs={"a": np.random.uniform}
            make sure to update the kwargs accordingly.
            for instance, t0: {"low":0, "high":10}

        **kwargs can change the model entry parameters
            for instance, t0: {"low":0, "high":10}
            will update model["t0"]["kwargs"] = ...

        Returns
        -------
        dict
           a copy of the model (with param potentially updated)
        """
        model = deepcopy(self.model)
        for k,v in kwargs.items():
            model[k]["kwargs"] = {**model[k].get("kwargs",{}), **v}

        return model
    
    def change_model(self, **kwargs):
        """ change the model attached to this instance
        
        **kwargs will update the entry  parameters ("param", e.g. t0["kwargs"])

        See also
        --------
        get_model: get a copy of the model
        """
        self.model = self.get_model(**kwargs)

    def get_func_parameters(self, valdefault="unknown"):
        """ get a dictionary with the parameters name of all model functions
        
        Parameters
        ----------
        valdefault: str, None
            value used with function inspection fails
            (like e.g. np.random.rand).

        Returns
        -------
        dict
        """
        import inspect
        inspected = {}
        for k, m in self.model.items():
            func = self._parse_input_func(name=k, func=m.get("func", None))
            try:
                params = inspect.getfullargspec(func).args
            except:
                params = valdefault
            inspected[k] = params

        return inspected
    
    def get_backward_entries(self, name, incl_input=True):
        """ get the list of entries that affects the input on.
        Changing any of the return entry name impact the given name.

        Parameters
        ----------
        name: str
            name of the entry

        incl_input: bool
            should the returned list include or not 
            the given name ? 

        Return
        ------
        list
            list of backward entry names 
        """
        depends_on = self.entry_dependencies.dropna()

        names = np.atleast_1d(name)
        if incl_input:
            backward_entries = list(names)
        else:
            backward_entries = []

        leads_to_changing = depends_on.loc[depends_on.index.isin(names)]
        while len(leads_to_changing)>0:
            _ = [backward_entries.append(name_) for name_ in list(leads_to_changing.values)]
            leads_to_changing = depends_on.loc[depends_on.index.isin(leads_to_changing)]

        return backward_entries

    def get_forward_entries(self, name, incl_input=True):
        """ get the list of forward entries. 
        These would be affected if the given entry name is changed.

        Parameters
        ----------
        name: str
            name of the entry

        incl_input: bool
            should the returned list include or not 
            the given name ? 

        Return
        ------
        list
            list of forward entry names 
        """
        inputs_of = self.entry_inputof.explode()

        names = np.atleast_1d(name)
        if incl_input:
            forward_entries = list(names)
        else:
            forward_entries = []

        leads_to_changing = inputs_of.loc[inputs_of.index.isin(names)]
        while len(leads_to_changing)>0:
            # all names individually
            _ = [forward_entries.append(name_) for name_ in list(leads_to_changing.values)]
            leads_to_changing = inputs_of.loc[inputs_of.index.isin(leads_to_changing)]

        return forward_entries


    def get_modeldf(self, explode=True):
        """ get a pandas.DataFrame version of the model dict

        Parameters
        ----------
        explode: bool
            should the input entry be exploded ?

        Returns
        -------
        pandas.DataFrame
        """
        modeldf = modeldict_to_modeldf(self.model)
        modeldf["input"] = modeldf["kwargs"].apply(lambda x: [] if type(x) is not dict else [l.split("@")[-1].split(" ")[0] for l in x.values() if type(l) is str and "@" in l])
        if not explode:
            return modeldf.explode("entry").set_index("entry")
        
        return modeldf.explode("entry").explode("input").set_index("entry")
        
    # ============ #
    #  Drawers     #
    # ============ #
    def redraw_from(self, name, data, incl_name=True, size=None, **kwargs):
        """ re-draw the data starting from the given entry name.
        
        All forward values will be updated while the independent 
        entries are left unchanged.

        Parameters
        ----------
        name: str, list
            entry name or names. See self.entries

        data: pandas.DataFrame
            data to be updated 
            Must at least include entry needed by name if any. 
            See self.entry_dependencies

        incl_name: bool
            should the given name be updated or not ?

        size: None
            number of entries to draw. Ignored if not needed.

        **kwargs goes to self.draw() -> get_model

        Returns
        -------
        pandas.DataFrame
            the updated version of the input data.

        """
        if len(np.atleast_1d(name)) > 1: # several entries
            # do not include the input entry at fist
            name = list(np.atleast_1d(name)) # as list 
            limit_to_entries = [self.get_forward_entries(name_, incl_input=False) for name_ in name]
            limit_to_entries = list(np.unique(np.concatenate(limit_to_entries))) # unique
            if np.any([name_ in limit_to_entries for name_ in name]): # means some entry want to change another given
                raise ValueError("At least on of the input name have at least one other given as forward entry. This is not supported by this method.")
            
            if incl_name:
                limit_to_entries += name
        else:
            limit_to_entries = self.get_forward_entries(name, incl_input=incl_name)
            
        return self.draw(size, limit_to_entries=limit_to_entries, data=data)

    
    def draw(self, size=None, limit_to_entries=None, data=None, **kwargs):
        """ draw a random sampling of the parameters following
        the model DAG

        Parameters
        ----------
        size: int
            number of elements you want to draw.


        limit_to_entries: list
            if given, entries not in this list will be ignored.
            see self.entries

        data: pandas.DataFrame
            starting point for the draw.

        **kwargs goes to get_model()

        Returns
        -------
        pandas.DataFrame
            N=size lines and at least 1 column per model entry
        """
        model = self.get_model(**kwargs)
        return self._draw(model, size=size, limit_to_entries=limit_to_entries,
                              data=data)
    
    def draw_param(self, name=None, func=None, size=None, xx=None, **kwargs):
        """ draw a single entry of the model

        Parameters
        ----------
        name: str
            name of the variable
            
        func: str, function
            what func should be used to draw the parameter

        size: int
            number of line to be draw

        xx: str, array
           provide this *if* the func returns the pdf and not sampling.
           xx defines where the pdf will be evaluated.
           if xx is a string, it will be assumed to be a np.r_ entry (``np.r_[xx]``)

        Returns
        -------
        list 
            
        """
        # Flexible origin of the sampling method
        func = self._parse_input_func(name=name, func=func)
        
        # Check the function parameters
        try:
            func_arguments = list(inspect.getfullargspec(func).args)
        except: # fail for Cython functions
            #warnings.warn(f"inspect failed for {name}{func} -> {func}")
            func_arguments = ["size"] # let's assume this as for numpy.random or scipy.

        # And set the correct parameters
        prop = {}
        if "size" in func_arguments:
            prop["size"] = size
            
        if "func" in func_arguments and func is not None: # means you left the default
            prop["func"] = func

        if "xx" in func_arguments and xx is not None: # if xx is None
            if type(xx) == str: # assumed r_ input
                xx = eval(f"np.r_[{xx}]")
                
            prop["xx"] = xx

        # Draw it.
        draw_ = func(**{**prop, **kwargs})
        if "xx" in func_arguments: # draw_ was actually a pdf
            xx_, pdf_ = draw_
            draw_ = self.draw_from_pdf(pdf_, xx_, size)
            
        return draw_
            
    @staticmethod
    def draw_from_pdf(pdf, xx, size):
        """ randomly draw from xx N=size elements following the pdf. """
        if type(xx) == str: # assumed r_ input
            xx = eval(f"np.r_[{xx}]")

        pdf = np.squeeze(pdf) # shape -> (1, size) -> (size,)
        
        if len( pdf.shape ) == 2:
            choices = np.hstack([np.random.choice(xx, size=1, p=pdf_/pdf_.sum())
                           for pdf_ in pdf])
        else:
            choices = np.random.choice(xx, size=size, p=pdf/pdf.sum())

        return choices
    

    def _draw(self, model, size=None, limit_to_entries=None, data=None):
        """ core method converting model into a DataFrame (interp) """
        
        model = deepcopy(model) # safe case
        if size == 0:
            columns = list(np.hstack([v.get("as", name) for name, v in model.items()]))
            return pandas.DataFrame(columns=columns)

        if data is None:
            data = pandas.DataFrame()
        else:
            data = data.copy() # make sure you are changing a copy

        #
        # The draw loop
        #
        
        for param_name, param_model in model.items():
            if limit_to_entries is not None and param_name not in limit_to_entries:
                continue

            params = dict(size=size) # starting point. This gets updated if @ arrives.
            # Default kwargs given
            if (inprop := param_model.get("kwargs", {})) is None:
                inprop = {}

            # parse the @**
            for k, v in inprop.items():
                if type(v) is str and "@" in v:
                    key = v.split("@")[-1].split(" ")[0]
                    inprop[k] = data[key].values
                    params["size"] = None
                    
            # set the model ; this overwrite prop['model'] but that make sense.
            inprop["func"] = param_model.get("func", None)
            
            # update the general properties for that of this parameters
            prop = {**params, **inprop}

            # 
            # Draw it
            samples = np.asarray(self.draw_param(param_name, **prop))

            # and feed
            output_name = param_model.get("as", param_name)
            if output_name is None: # solves 'as' = None case.
                output_name = param_name
            data[output_name] = samples.T

        return data
    
    def _parse_input_func(self, name=None, func=None):
        """ returns the function associated to the input func.

        """
        if callable(func): # func is a function. Good to go.
            return func
        
        # func is a method of this instance ?
        if func is not None and hasattr(self, func):
            func = getattr(self, func)
            
        # func is a method a given object ?
        elif func is not None and hasattr(self.obj, func):
            func = getattr(self.obj, func)
            
        # name is a draw_ method of this instance object ?            
        elif hasattr(self, f"draw_{name}"):
            func = getattr(self,f"draw_{name}")

        # name is a draw_ method of this instance object ?            
        elif hasattr(self.obj, f"draw_{name}"):
            func = getattr(self.obj, f"draw_{name}")
        
        else:
            try:
                func = eval(func) # if you input a string of a function known by python somehow ?
            except:
                raise ValueError(f"Cannot parse the input function {name}:{func}")
        
        return func

    # =================== #
    #   Properties        #
    # =================== #
    @property
    def entries(self):
        """ array of model entry names """
        modeldf = self.get_modeldf()
        return np.asarray(modeldf.index.unique(), dtype=str)

    @property
    def entry_dependencies(self):
        """ pandas series of entry input dependencies (exploded) | NaN is not entry """
        modeldf = self.get_modeldf()
        return modeldf["input"]

    @property
    def entry_inputof(self):
        """ """
        # maybe a bit overcomplicated...
        modeldf = self.get_modeldf()
        return modeldf[~modeldf["input"].isna()].reset_index().set_index("input")["entry"]
        
