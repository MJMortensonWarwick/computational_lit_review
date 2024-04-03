import bertopic
import pandas as pd
from wordcloud import WordCloud
import plotly.express as px
import kaleido
import rispy

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph

import matplotlib.pyplot as plt
import textwrap


def file_loader(ris_file, nbook="colab", source="scopus"):
    '''
    FUNCTION to load a file from ris format and prepare for a clr analysis
    INPUT: a RIS format export from an academic database (tested on Scopus and WoS)
    OUTPUT: a prepared corpus with citations extracted and column names fixed
    '''
  
    # adjust path if using a colab notebook
    if nbook == "colab":
        if 'content/' not in ris_file:
            ris_file = '/content/' + ris_file

    with open(ris_file, 'r') as file:
        entries = rispy.load(file)

    temp_df = pd.DataFrame(entries)

    # filter to just the relevant fields
    corpus = temp_df[[
      'doi', 'title', 'authors', 'year', 'secondary_title', 'volume',
      'start_page', 'end_page', 'abstract', 'notes', 'type_of_reference']]

    # rename
    corpus = corpus.rename(columns={
      'doi': 'DOI', 'title': 'Title', 'authors': 'Authors', 'year': 'Year',
      'secondary_title': 'Source', 'volume': 'Volume', 'start_page': 'Start',
      'end_page': 'End', 'abstract': 'Abstract', 'notes': 'Citations',
      'type_of_reference': 'Type'
    })

    # TODO - work out a decent deduplication strategy
    # drop duplicates based on DOI
    # corpus = corpus.drop_duplicates(subset='DOI')

    # seperate out citations from the text
    if source == "scopus":
        corpus['Citations'] = corpus['Citations'].str[0].str.split(';')
        corpus['Citations'] = corpus['Citations'].str[1].str.replace("Cited By: ", "").astype(int)
    elif source == "wos":
        corpus['Citations'] = corpus['Citations'].str[1].str.split(': ')
        corpus['Citations'] = corpus['Citations'].str[1].astype(int)

    # convert numeric columns to a numeric data type
    num_cols = ['Year', 'Citations']
    for col in num_cols:
        corpus[col] = pd.to_numeric(corpus[col])

    return corpus


def corpus_eda(file, viz="all", save=True, nbook="colab"):
    '''
    FUNCTION to produce eda/visualisations of the data input
    INPUT: a corpus generated by the file_loader function (from ris)
    OUTPUT: a dictionary of visualisations and, (if save == True)
    a folder of all the visualisations
    '''

    # if colab then create folders based on the colab directory structure
    if nbook == "colab" and save:
        import os
        # if folder already exists rename by adding a timestamp
        if os.path.isdir('/content/eda'):
            from datetime import datetime
            new_name = '/content/eda' + str(datetime.utcnow())
            os.rename('/content/eda', new_name)
        os.mkdir("/content/eda")
        os.chdir("/content/eda")
    # if not colab but save then create on a local machine 
    elif save:
        import os
        if os.path.isdir('/eda'):
            from datetime import datetime
            new_name = '/eda' + str(datetime.utcnow())
            os.rename('/eda', new_name)
        os.mkdir("/eda")
        os.chdir("/eda")

    return_dict = {} # empty dictionary to return visualisation

    # Publications by Year
    if viz == "all" or "pubs_by_year":
        tempdf = file.groupby(["Year"]).size().to_frame(name = "Publications").reset_index()
        tempdf = tempdf.sort_values(by="Year")
        fig = px.line(tempdf, x="Year", y="Publications", title="Publications by Year")
        fig.update_xaxes(type="category")

        return_dict["pubs_by_year"] = fig

        if save:
            fig.write_html("pubs_by_year.html")
            fig.write_image("pubs_by_year.png")
            tempdf.to_csv("pubs_by_year.csv", index=False)

    # Citations by Year
    if viz == "all" or "cites_by_year":
        tempdf = file["Citations"].groupby(file["Year"]).mean().to_frame(name = "Citations").reset_index()
        tempdf = tempdf.sort_values(by="Year")
        fig = px.line(tempdf, x="Year", y="Citations", title="Average Citations by Year")
        fig.update_xaxes(type="category")

        return_dict["cites_by_year"] = fig
    
        if save:
            fig.write_html("cites_by_year.html")
            fig.write_image("cites_by_year.png")
            tempdf.to_csv("cites_by_year.csv", index=False)

    # Top papers by citations
    if viz == "all" or "top_paper_cites":
        tempdf = file.sort_values(by=['Citations'], ascending=False) # sort by "Citations"
        tempdf_sset = tempdf[:20] # extract just the top 20 rows
        tempdf_sset["Title"] = tempdf_sset.Title.str[0:50] + "  "
        tempdf_sset["Year"] = tempdf_sset.Year.astype(str)
        fig = px.bar(tempdf_sset, x="Citations", y="Title", color="Year",
                 orientation="h", title="Top 20 Papers by Citations")

        fig.update_layout(yaxis={'categoryorder':'total ascending'})

        return_dict["top_paper_cites"] = fig
    
        if save:
            fig.write_html("top_paper_cites.html")
            fig.write_image("top_paper_cites.png")
            tempdf[:100].to_csv("top_paper_cites.csv", index=False) # return top 100

    # Top authors by citation
    if viz == "all" or "top_author_cites":
        authors = file[['Authors', "Citations"]]
 
        # explode the data to one row per author per paper
        authors = authors.explode('Authors')

        # sum up the number of citations per author and rename column
        tempdf = authors.groupby(['Authors']).sum().reset_index()
        tempdf = tempdf.sort_values(by=['Citations'], ascending=False)

        # as above, sort the data by citations, select the top 20 and print/save the figure
        tempdf_sset = tempdf.head(20).reset_index()

        fig = px.bar(tempdf_sset, x="Citations", y="Authors", orientation="h",
                 title="Top 20 Authors by Citations")

        fig.update_layout(yaxis={'categoryorder':'total ascending'})

        return_dict["top_author_cites"] = fig
    
        if save:
            fig.write_html("top_author_cites.html")
            fig.write_image("top_author_cites.png")
            tempdf[:100].to_csv("top_author_cites.csv", index=False)

    # Top authors by h-index
    if viz == "all" or "top_author_hindex":
        # subset the file based on authors
        authors = file[['Authors', "Citations"]]

        # explode the data to one row per author per paper
        authors = authors.explode('Authors')

        # calculate h-index from the "exploded" (one row per author) dataframe
        authors['h-index'] = authors.groupby("Authors")["Citations"].transform( lambda x: (x >= x.count()).sum() )

        # reduce the dataframe to one row per author
        tempdf = authors.groupby(["Authors"]).max().reset_index()

        # sum up the number of citations per author and rename column
        tempdf = tempdf.sort_values(by=["h-index"], ascending=False)

        # as above, sort the data by citations, select the top 20 and print/save the figure
        tempdf_sset = tempdf.head(20).reset_index()
    
        fig = px.bar(tempdf_sset, x="h-index", y="Authors", orientation="h",
                 hover_data=["Citations"], title="Top 20 Authors by h-index")

        fig.update_layout(yaxis={'categoryorder':'total ascending'})

        return_dict["top_author_hindex"] = fig
    
        if save:
            fig.write_html("top_author_hindex.html")
            fig.write_image("top_author_hindex.png")
            tempdf[:100].to_csv("top_author_hindex.csv", index=False)

    # Top sources by citation
    if viz == "all" or "top_sources_cites":
        sources = file[["Source", "Citations"]]

        # sum up the number of citations per author and rename column
        tempdf = sources.groupby(["Source"]).sum().reset_index()
        tempdf = tempdf.sort_values(by=['Citations'], ascending=False)

        # as above, sort the data by citations, select the top 20 and print/save the figure
        tempdf_sset = tempdf.head(20).reset_index()
        # reduce source title to 50 characters
        tempdf_sset["Source"] = tempdf_sset.Source.str[0:50] + "  "

        fig = px.bar(tempdf_sset, x="Citations", y="Source", orientation="h",
                 title="Top 20 Sources by Citations")

        fig.update_layout(yaxis={'categoryorder':'total ascending'})

        return_dict["top_source_cites"] = fig
    
        if save:
            fig.write_html("top_source_cites.html")
            fig.write_image("top_source_cites.png")
            tempdf[:100].to_csv("top_source_cites.csv", index=False)

    # Top journals by h-index
    if viz == "all" or "top_source_hindex":
        # subset the file based on sources
        sources = file[["Source", "Citations"]]

        # calculate h-index
        sources['h-index'] = sources.groupby('Source')['Citations'].transform( lambda x: (x >= x.count()).sum() )

        tempdf = sources.groupby(['Source']).max().reset_index()

        # sum up the number of citations per author and rename column
        tempdf = tempdf.sort_values(by=["h-index"], ascending=False)

        # sort the data by citations & select the top 20
        tempdf_sset = tempdf.head(20).reset_index()
        # reduce source title to 50 characters
        tempdf_sset["Source"] = tempdf_sset.Source.str[0:50] + "  "

        fig = px.bar(tempdf_sset, x="h-index", y="Source", orientation="h",
                 hover_data=["Citations"], title="Top 20 Sources by h-index")

        fig.update_layout(yaxis={'categoryorder':'total ascending'})

        return_dict["top_source_hindex"] = fig
    
        if save:
            fig.write_html("top_source_hindex.html")
            fig.write_image("top_source_hindex.png")
            tempdf[:100].to_csv("top_source_hindex.csv", index=False)


    return return_dict


def hyperP_scaler(corpus):
    '''
    FUNCTION to dynamically set hyperparameters for BERTopic based on dataset size
    INPUT: a dataset of text (a corpus)
    OUTPUT: min_topic_size and n_neighbors (for UMAP) hyperparameter choices
    '''
    topic_size = int(len(corpus) / 2000 * 10) + 1
    umap_size = int(len(corpus) / 2000 * 15) + 1
    return topic_size, umap_size


def topic_model(corpus, embed_model="miniLM", rep_model="keybert", n_topics="auto", seed=123):
    '''
    FUNCTION to specify the neural topic model
    INPUT: a corpus and set of hyperparameters
    OUTPUT: a specified topic model 
    '''
    # determine embedding model
    from sentence_transformers import SentenceTransformer, util
    if embed_model == "miniLM":
        embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    # specter as a model pretrained on academic abstracts
    elif embed_model == "specter":
        embedding_model = SentenceTransformer("allenai-specter")
    else:
        embedding_model = SentenceTransformer(embed_model)

    # determine representation model
    if rep_model == "keybert":
        representation_model = bertopic.representation.KeyBERTInspired()
    # TODO - add in other representation models that can be used

    # set topics and define model
    if n_topics == "auto":
        # automatically calculate min topics and umap size
        min_topics, n_umap = hyperP_scaler(corpus)

        # specify UMAP implementation with or without seed (repeatability) using defaults
        if seed != None:
            from umap import UMAP
            umap_model = UMAP(n_neighbors=n_umap, min_dist=0.0, metric='cosine',
                      low_memory=False, random_state=seed)
        else:
            from umap import UMAP
            umap_model = UMAP(n_neighbors=n_umap, min_dist=0.0, metric='cosine',
                      low_memory=False)

        # final topic model
        topic_model = bertopic.BERTopic(min_topic_size=min_topics,
                                    embedding_model=embedding_model,
                                    representation_model=representation_model,
                                    umap_model=umap_model)
    
    # if topics are specified
    else:

        if seed != None:
            from umap import UMAP
            umap_model = UMAP(n_neighbors=15, min_dist=0.0, metric='cosine',
                      low_memory=False, random_state=123) # default params
        else:
            from umap import UMAP
            umap_model = UMAP(n_neighbors=15, min_dist=0.0, metric='cosine',
                      low_memory=False) # default params

        # define the topic model and hyperparameters
        topic_model = bertopic.BERTopic(nr_topics=n_topics,
                                    embedding_model=embedding_model,
                                    representation_model=representation_model)

    return topic_model


def fit_topic_model(corpus, topic_model):
    '''
    FUNCTION to fit a topic model to a corpus
    INPUT: a corpus and a topic model specified by the topic_model function
    OUTPUT: a fitted topic model (with topics and probabilities)
    '''
  
    corpus = corpus.dropna(subset=['Abstract'])
    docs = corpus['Abstract'] # use the abstracts as the text data (corpus)

    topics, probabilities = topic_model.fit_transform(docs)

    return corpus, topics, probabilities


def drop_topics(corpus, model, n_topics='auto'):
    '''
    FUNCTION to reduce the size of the topic model (k - number of topics)
    either automatically
    INPUT: a corpus and topic model
    OUTPUT: a reduced to topic model to either a specified value of k or an automated size reduction
    '''
    
    docs = corpus['Abstract']

    # if n_topics is specified
    if n_topics != 'auto':
        new_model = model.reduce_topics(docs, nr_topics=n_topics)
    # if n_topics is NOT specified
    else:
        new_model = model.reduce_topics(docs)

    return new_model


def create_wordcloud(model, topic):
    '''
    FUNCTION to create a wordcloud for a topic
    INPUT: a model and specific topic to visulaise
    OUTPUT: a wordcloud for the topic
    '''
    
    text = {word: value for word, value in model.get_topic(topic)}
    wc = WordCloud(background_color="white", max_words=1000)
    wc.generate_from_frequencies(text)
    plt.imshow(wc, interpolation="bilinear")
    plt.axis("off")
    return plt


def topic_report(model, corpus):
    '''
    FUNCTION to create the topic report for a model
    INPUT: a corpus and a model
    OUTPUT: a full topic report as PDF
    '''
    
    # specify number of pages as the number of topics
    end_page = len(model.topic_labels_)-1 # ignore outlier topic

    # create topic labels - i.e. keywords
    topic_labels = model.generate_topic_labels(nr_words=10, # increase to 10 words per topic
                                              topic_prefix=False,
                                              word_length=10,
                                              separator=", ")

    # specify the output document and dimensions
    c = canvas.Canvas("topic_report.pdf", pagesize=A4)
    w, h = A4

    # create combined df
    docs = corpus['Abstract']
    topic_distr, _ = model.approximate_distribution(docs)
    # extract the labels for each topic
    col_names = [*model.topic_labels_.values()]
    # build a dataframe of topic proportions (row as records, columns as topics)
    topics_df = pd.DataFrame(topic_distr, columns=col_names[1:])
    # combine
    output = pd.concat([corpus.reset_index(drop=True), topics_df.reset_index(drop=True)], axis=1)

    # loop through each topic writing the content
    for i in range(0, end_page):
        text = c.beginText(40, h - 50)
        text.setFont('Helvetica-Bold', 10)
        text.textLine(f'Topic #{i}')
        text.textLine(" ")
        text.textLine("Word Cloud")
        c.drawText(text)

        # Wordclouds
        cloud = create_wordcloud(model, topic=i) # create a wordcloud of topic i
        cloud.savefig(f'cloud_topic{i}.png', bbox_inches='tight')
        img = ImageReader(f'cloud_topic{i}.png')
        # Get the width and height of the image.
        img_w, img_h = img.getSize()
        # h - img_h is the height of the sheet minus the height of the image.
        c.drawImage(img, 40, h - img_h - 80)

        # Keywords
        text = c.beginText(40, h - 370)
        text.setFont('Helvetica-Bold', 10)
        text.textLine("Topic Keywords")
        text.setFont('Helvetica', 10)
        keywords = topic_labels[i+1]
        text.textLine(keywords)
        text.textLine(" ")

        # Sources
        col_name = list(model.topic_labels_.values())[i+1]
        journals_temp = output[["Source", col_name]]
        # sum up the number of citations per source and sort
        journals = journals_temp.groupby(["Source"]).sum().reset_index()
        journals = journals.sort_values(by=[col_name], ascending=False)
        text.setFont('Helvetica-Bold', 10)
        text.textLine("Top Sources")
        text.setFont('Helvetica', 8)
        wrapper = textwrap.TextWrapper(width=140)
        # loop through the top five journals
        for journal in range(0, 5):
            j_title = journals.iloc[journal]["Source"]
            word_list = wrapper.wrap(text=j_title)
            # loop through words in journal title
            for element in word_list:
                text.textLine(element)
        text.textLine(" ")

        # Papers
        col_name = list(model.topic_labels_.values())[i+1]
        papers = output.sort_values(by=[col_name], ascending=False)
        
        text.setFont('Helvetica-Bold', 10)
        text.textLine("Top Publications")
        text.setFont('Helvetica', 8)
        wrapper = textwrap.TextWrapper(width=140)
        # loop through the top five papers
        for paper in range(0, 5):
            p_title = papers.iloc[paper]["Title"]
            word_list = wrapper.wrap(text=p_title)
            # loop through words in title
            for element in word_list:
                text.textLine(element)
        text.textLine(" ")

        # Abstracts
        text.setFont('Helvetica-Bold', 10)
        text.textLine("Representative Abstracts")
        text.setFont('Helvetica', 8)
        wrapper = textwrap.TextWrapper(width=140)
        for doc in model.representative_docs_[i]:
            # if more than 800 characters truncate
            if len(doc) > 800:
                doc = doc[:800]
                doc += '...'
            word_list = wrapper.wrap(text=doc)
            # loop through words in abstract
            for element in word_list:
                text.textLine(element)
        text.textLine(" ")

        c.drawText(text)

        c.showPage()

    # once complete save the document
    c.save()


def topic_outputs(corpus, model, topics, viz="all", save=True, nbook="colab"):
    '''
    FUNCTION to create visualisations of the topic outputs
    INPUT: a corpus and topic model
    OUTPUT: one or more visualisation(s) potentially saved as a folder 
    '''

    if nbook == "colab" and save:
        import os
        if os.path.isdir('/content/output'):
            from datetime import datetime
            new_name = '/content/output' + str(datetime.utcnow())
            os.rename('/content/output', new_name)
        os.mkdir("/content/output")
        os.chdir("/content/output")
    elif save:
        import os
        if os.path.isdir('/output'):
            from datetime import datetime
            new_name = '/output' + str(datetime.utcnow())
            os.rename('/output', new_name)
        os.mkdir("/output")
        os.chdir("/output")

    return_dict = {} # empty dictionary to return visualisation

    # Distance map
    if viz == "all" or "distance_map":
        fig = model.visualize_topics()

        return_dict["distance_map"] = fig

        if save:
            fig.write_image("distance_map.png")
            fig.write_html("distance_map.html")

    # Topic barcharts
    if viz == "all" or "topic_bar":
        # subtract 1 to remove the outliers
        fig = model.visualize_barchart(top_n_topics=len(model.topic_labels_)-1)

        return_dict["topic_bar"] = fig

        if save:
            fig.write_image("topic_bar.png")
            fig.write_html("topic_bar.html")

    # Similiarity matrix
    if viz == "all" or "similarity_matrix":
        fig = model.visualize_heatmap()

        return_dict["similarity_matrix"] = fig

        if save:
            fig.write_image("similarity_matrix.png")
            fig.write_html("similarity_matrix.html")

    # Topic dataframe
    if viz == "all" or "topics_df":
        docs = corpus['Abstract']
        topic_distr, _ = model.approximate_distribution(docs)

        # extract the labels for each topic
        col_names = [*model.topic_labels_.values()]

        # build a dataframe of topic proportions (row as records, columns as topics)
        topics_df = pd.DataFrame(topic_distr, columns=col_names[1:])

        output = pd.concat([corpus.reset_index(drop=True), topics_df.reset_index(drop=True)], axis=1) # axis 1 means adding as columns (to the right)

        output.to_csv("topics_df.csv", index=False)

    if viz == "all" or "topic_report":
        topic_report(model, corpus)

    # return everything
    return return_dict


def form_display(model):
    '''
    FUNCTION to create a set of form items (sliders) to weight each element.
    INPUT: a model
    OUTPUT: a dictionary of form items that values can be extracted from.
    '''
    import ipywidgets as widgets

    # define an ouput UI
    out = widgets.Output(layout={'border': '1px solid black'})

    sliders_dict = {} # empty dictionary

    with out:
        print('\n')
        print('  Use the following sliders to weight the following aspects (higher means greater weight):')
        print('\n')
        # citations
        print('  Number of citations')
        sliders_dict['cites'] = widgets.IntSlider(value=0,
            min=0,
            max=10,
            step=1)
        display(sliders_dict['cites']) # add to output
        print('\n')
        # recency
        print('  Recency of publication')
        sliders_dict['recency'] = widgets.IntSlider(value=0,
            min=0,
            max=10,
            step=1)
        display(sliders_dict['recency'])
        print('\n')
        # topics
        print('  Topics')
        sliders_dict['topics'] = widgets.IntSlider(value=10,
            min=0,
            max=10,
            step=1)
        display(sliders_dict['topics'])
        print('\n')
        # individual topics
        print('  Use the following sliders to weight the different topics (higher means greater weight):')
        print('\n')
        topic_names = [*model.topic_labels_.values()]
        for i in range(len(model.topic_labels_)-1):
            print('  ' + topic_names[i+1])
            sliders_dict[topic_names[i+1]] = widgets.IntSlider(value=5,
                min=0,
                max=10,
                step=1)
            display(sliders_dict[topic_names[i+1]])
            print('\n')

    return {'output': out, 'sliders_dict': sliders_dict}


def value_updates(display_form):
    '''
    FUNCTION to update the values from the form
    INPUT: a dictionary of form items generated by the form_display function
    OUTPUT: a dictionary of weights for each item
    '''
    
    values_dict = {}
    for key in display_form['sliders_dict']:
        values_dict[key] = display_form['sliders_dict'][key].value / 10

    return values_dict


def inclusion_criteria(corpus, model, weights, include_scores=False):
    '''
    FUNCTION to weight every paper in a corpus
    INPUT: a corpus, model and set of weights per item
    OUTPUT: a ranked corpus (dataframe) of papers
    '''
    
    docs = corpus['Abstract']
    topic_distr, _ = model.approximate_distribution(docs)

    # extract the labels for each topic
    col_names = [*model.topic_labels_.values()]

    # build a dataframe of topic proportions (row as records, columns as topics)
    topics_df = pd.DataFrame(topic_distr, columns=col_names[1:])

    output = pd.concat([corpus.reset_index(drop=True), topics_df.reset_index(drop=True)], axis=1) # axis 1 means adding as columns (to the right)

    score_list = [] # keep track of topic variables

    for key in weights:
        if key == 'cites':
            # normalise citations
            output['cite_score'] = (output['Citations'] - output['Citations'].min()) / (output['Citations'].max() - output['Citations'].min())
            # adjust by weight
            output['cite_score'] = output['cite_score'] * weights[key]
        elif key == 'recency':
            output['recency_score'] = (output['Year'] - output['Year'].min()) / (output['Year'].max() - output['Year'].min())
            output['recency_score'] = output['recency_score'] * weights[key]
        # loop through topics
        elif key != 'topics':
            field_name = key + 'W' # dummy column name to avoid duplication
            output[field_name] = output[key] * weights[key]
            score_list.append(field_name)

    # sum up all topic scores by weights
    output['topic_score'] = output[score_list].sum(axis=1)
    # normalise the topic scores
    output['topic_score'] = (output['topic_score'] - output['topic_score'].min()) / (output['topic_score'].max() - output['topic_score'].min())
    # adjust for overall topic weight
    output['topic_score'] = output['topic_score'] * weights['topics']

    # calculate overall score
    output['score'] = output['cite_score'] + output['recency_score'] + output['topic_score']

    # sort df by score variable
    output = output.sort_values(by=['score'], ascending=False)

    # delete score columns unless specified otherwise
    if include_scores == False:
        output = output.drop(output[score_list], axis=1)

    return output


def return_included_papers(n='all', corpus, model, topic_weights, ris_file=None, nbook='colab', save=True):
    '''
    FUNCTION to return a certain number of papers according to user input
    INPUT: a corpus, model, set of weights and number of papers to shortlist
    OUTPUT: a shortlisted corpus in dataframe and ris format
    '''

    # if colab then create folders based on the colab directory structure
    if nbook == "colab" and save:
        import os
        # if folder already exists rename by adding a timestamp
        if os.path.isdir('/content/sources'):
            from datetime import datetime
            new_name = '/content/sources' + str(datetime.utcnow())
            os.rename('/content/sources', new_name)
        os.mkdir("/content/sources")
        os.chdir("/content/sources")
    # if not colab but save then create on a local machine 
    elif save:
        import os
        if os.path.isdir('/sources'):
            from datetime import datetime
            new_name = '/sources' + str(datetime.utcnow())
            os.rename('/sources', new_name)
        os.mkdir("/sources")
        os.chdir("/sources")

    
    # create dataframe
    ranked_df = inclusion_criteria(corpus, model, topic_weights)
    if n != 'all':
        ranked_df = ranked_df.head(n)
    ranked_df.to_csv("ranked_df.csv", index=False)

    # create ris file
    if ris_file != None:
        if nbook == "colab":
            if 'content/' not in ris_file:
                ris_file = '/content/' + ris_file

        with open(ris_file, 'r') as file:
            entries = rispy.load(file)
        
        # convert ris file to a dataframe
        temp_df = pd.DataFrame(entries)

        # merge ris dataframe with score columns from ranked_df
        merged_df = temp_df.merge(
            ranked_df[['Title', 'Source', 'score', 'cite_score', 'recency_score', 'topic_score']], 
            how='right', left_on=['title', 'secondary_title'], right_on=['Title', 'Source'])
        
        merged_df = merged_df.sort_values(by=['score'], ascending=False) # sort by score
        merged_df = merged_df.drop(['Title', 'Source'], axis=1) # drop extra DOI column

        # change column names to match ris format
        merged_df = merged_df.rename(columns={
            'score': 'custom1', 'cite_score': 'custom2', 'recency_score': 'custom3', 
            'topic_score': 'custom4'
        })

        # rename any nan's as 'none'
        merged_df = merged_df.fillna(value="none")

        # output to ris format again
        out = merged_df.to_dict('records')
        filepath = 'export.ris'
        with open(filepath, 'w') as out_file:
            rispy.dump(out, out_file)
            
    return ranked_df

def prompt_template(k, model):
    labels = [*model.topic_labels_.values()]
    keywords = labels[k]
    documents = []
    for doc in model.representative_docs_[i]:
        # if more than 800 characters truncate
        if len(doc) > 800:
            doc = doc[:800]
        documents.append(doc)
    print("I have topic that contains the following documents:\n {documents} 
        \n The topic is described by the following keywords: " + keywords + 
        "\n Based on the above, can you give a short label of the topic?")
