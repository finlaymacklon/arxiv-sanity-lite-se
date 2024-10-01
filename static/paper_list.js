'use strict';


const Paper = props => {
    const p = props.paper;
    const similar_url = "/?rank=pid&pid=" + p.id;
    const inspect_url = "/inspect?pid=" + p.id;
    // provide the correct href depending on what the id is set as
    let url_base = null;
    if (p.id.includes("http://") || p.id.includes("https://")) {
        url_base = '';
    } else if (p.id.includes("/")) {
        url_base = 'https://doi.org/';
    } else {
        url_base = 'http://arxiv.org/abs/';
    };
    return (
    <div class='rel_paper'>
        <div class="rel_score">{p.weight.toFixed(2)}</div>
        <div class='rel_title'><a href={url_base + p.id}>{p.title}</a></div>
        <div class='rel_authors'>{p.authors}</div>
        <div class="rel_time">{p.time}</div>
        <div class='rel_abs'>{p.summary}</div>
        <div class='rel_more'><a href={similar_url}>similar</a></div>
        <div class='rel_inspect'><a href={inspect_url}>inspect</a></div>
    </div>
    )
}

const PaperList = props => {
    const lst = props.papers;
    const plst = lst.map((jpaper, ix) => <Paper key={ix} paper={jpaper} />);
    return (
        <div>
            <div id="paperList" class="rel_papers">
                {plst}
            </div>
        </div>
    )
}

// render papers into #wrap
ReactDOM.render(<PaperList papers={papers} />, document.getElementById('wrap'));
